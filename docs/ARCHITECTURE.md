# NetWatch Architecture

## Components

**Zeek** — The capture and protocol-analysis brain. Runs either as a live sniffer (`zeek -i eth0`) or as a PCAP replay loop. Produces one JSON object per network event per protocol, written to rotating files in `/logs`.

**Filebeat** — A thin, reliable shipping agent. Tails Zeek's JSON logs, normalizes the `ts` field to `@timestamp`, drops noisy metadata, and publishes each event to a per-protocol Kafka topic. Handles file rotation, offset tracking, and retries so the processor never has to touch disk.

**Kafka (+ Zookeeper)** — The durable buffer. Decouples ingest from processing, gives us parallelism via partitions, and lets us replay traffic for debugging. Topics are per-protocol so the processor can scale them independently.

**Python Processor (FastAPI)** — The enrichment / detection brain. One async Kafka consumer per topic inside a single FastAPI process. Each event is parsed with Pydantic, tagged with `ip_classification`, run through detectors, and bulk-indexed to OpenSearch. Also exposes a small REST API for the React dashboard and `/metrics` for OTEL scraping.

**OpenSearch** — The searchable store. Strict index templates keep IPs, ports, and timestamps correctly typed. Indices are date-stamped per day; alerts go to a single `netwatch-alerts` index with a 7-day ISM policy.

**OpenTelemetry Collector** — The observability plane for the platform itself. Scrapes Prometheus metrics from the processor, receives OTLP traces/logs, and fans out to OpenSearch + Grafana.

**Grafana** — Analytics dashboards and alert rules. Reads OpenSearch for event data and Prometheus-format metrics from the OTEL collector.

**Postgres** — Reserved for stateful control-plane data (config overrides, audit log, user sessions). Not in the hot path for events.

**React frontend** — Operator-focused control panel (overview, alerts, explorer, settings). Talks only to the FastAPI processor over HTTP.

## Data flow — a single packet's journey

1. A packet hits the interface Zeek is listening on.
2. Zeek's protocol analyzer classifies it (conn, dns, http, ssl). Within ~60 seconds Zeek rotates `conn.log` and a fresh file is written with one JSON object per flow.
3. Filebeat detects the new file (5s scan), parses each JSON line, drops noise fields, and publishes to `zeek-conn` (or dns/http) with `codec.json` + gzip compression.
4. Kafka replicates it to its assigned partition.
5. The Python processor's `ConnConsumer` (group `netwatch-processor-conn`) polls and receives the message. It validates the payload against `ConnEvent`, looks up the source IP's classification via the cached `classify_ip()`, and runs it through `HighVolumeDetector` and `PortScanDetector`.
6. If either detector fires, an alert dict is published to `zeek-alerts` via the idempotent Kafka producer, and the enriched document's `alert_type` is set.
7. The document is added to the `OpenSearchExporter` buffer; when the buffer hits 100 items (or 5 s elapses) it bulk-indexes to `netwatch-conn-YYYY.MM.DD`.
8. Grafana's 10-second refresh picks the new document up in the next dashboard query. Any matching alert rule evaluates and fires.
9. Operators see a red badge on the Alerts page of the React dashboard, which is polling `/api/alerts` every 10 seconds.

## Why these technologies

- **Zeek vs Suricata.** Both are capable NSM engines; Zeek is chosen for its richer protocol-level semantics (clean `conn.log` with connection state, DNS query fields, HTTP method/host/URI parsed out) and scriptability. Suricata is better if you need signature-based IDS.
- **Kafka vs direct file tail / direct DB writes.** Kafka buys us replay, backpressure tolerance, and independent scaling. If the processor crashes, events queue in Kafka; if the processor falls behind, lag shows up as a metric instead of a data loss event.
- **OpenSearch vs Elasticsearch.** OpenSearch is Apache-2.0 licensed, has a free distro, and a maintained OTEL exporter. Operationally equivalent for our use case.
- **FastAPI vs Go.** Python + FastAPI keeps detectors easy to iterate on (the core value is in detection logic, not throughput). At >50k events/sec the enrichment layer would want to move to Go or Rust.

## What breaks first at scale

Roughly in order of failure:

1. **Python detector state.** The sliding-window counters live in in-process `dict` / `deque`. At high per-IP cardinality they balloon memory. **Fix:** move to Redis with TTL keys, or a Kafka Streams / Flink windowed aggregation.
2. **OpenSearch bulk indexing.** Single-node OpenSearch on one shard saturates at ~5–10k docs/sec. **Fix:** multi-node cluster, 3+ primary shards per index, ILM rollover by size.
3. **Kafka consumer lag.** A single-process consumer can't keep up. **Fix:** scale the processor horizontally; topics are partitioned (3) so up to 3 consumers per topic can parallelize trivially.
4. **Filebeat file rotation races.** At high log rotation frequency Filebeat can double-read or miss lines. **Fix:** use Zeek's Kafka output plugin directly once the processor side is ready for exactly-once semantics.
5. **Zeek single-threaded packet processing.** Beyond ~1 Gbps Zeek needs PF_RING / AF_PACKET fanout and Zeek cluster mode (worker nodes + proxy + manager).
