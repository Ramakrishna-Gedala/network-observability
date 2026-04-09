# NetWatch — End-to-End Learning Guide

> A guided tour for someone seeing this project for the first time. You'll learn what every component does, why it exists, how a single network event flows through the system, and how to debug each stage independently. Read top to bottom and you'll have a complete mental model in about 30 minutes.

---

## Table of contents

1. [The 30-second pitch](#1-the-30-second-pitch)
2. [Why each piece exists](#2-why-each-piece-exists)
3. [The full pipeline diagram](#3-the-full-pipeline-diagram)
4. [Following one packet through the system](#4-following-one-packet-through-the-system)
5. [Component deep dives](#5-component-deep-dives)
6. [Where each config lives](#6-where-each-config-lives)
7. [Hands-on exercises](#7-hands-on-exercises)
8. [Debugging by symptom](#8-debugging-by-symptom)
9. [Vocabulary you should know](#9-vocabulary-you-should-know)
10. [Where to read next](#10-where-to-read-next)

---

## 1. The 30-second pitch

NetWatch is a **network observability platform**. It answers questions like:

- "Which IPs talked to which IPs in the last hour?"
- "Are any hosts behaving like a port scanner?"
- "Did anyone make an unusually long DNS query that might be tunneling data out?"
- "What's our top destination port? Top user agent? Most common HTTP status?"

It does this by running an open-source network monitor (**Zeek**) on captured traffic, transforming the events through a streaming pipeline (**Kafka → Python**), storing them in a search engine (**OpenSearch**), and visualizing them in dashboards (**Grafana**) plus a custom React control panel.

The whole thing is one `make up` away on any laptop with Docker.

---

## 2. Why each piece exists

A network observability stack has four jobs: **capture**, **transport**, **process**, **store/visualize**. Each tool in NetWatch has exactly one job:

| Tool | Job | Why this tool? |
|---|---|---|
| **Zeek** | Capture | Open-source, protocol-aware (parses HTTP, DNS, SSL fields automatically), JSON output, scriptable. Industry standard for NSM (Network Security Monitoring). |
| **Filebeat** | Transport (file → Kafka) | Reliable file tailing with offset tracking, file rotation handling, gzip compression. We don't have to write any of that ourselves. |
| **Kafka** | Buffer | Durable, replayable, partitioned. Decouples producers from consumers so neither has to wait for the other. |
| **Python (FastAPI)** | Process | Easy to write enrichment and detection logic. Great for iterating on rules. Slow at 10 Gbps, but we're not running at 10 Gbps. |
| **OpenSearch** | Store + search | Apache-2.0 licensed (no vendor lock-in), Elasticsearch-compatible API, great aggregations for security analytics. |
| **Grafana** | Visualize | The de facto open dashboard tool. Talks to OpenSearch and Prometheus directly. |
| **OpenTelemetry Collector** | Observability of the platform itself | One pipe for metrics + traces + logs *about* NetWatch (not the network traffic). |
| **React + FastAPI** | Operator control | Browser UI for tuning thresholds, pausing consumers, browsing recent alerts. Talks only to the FastAPI side. |
| **Postgres** | Reserved control-plane state | Not used yet. Future home for config persistence and audit trails. |

You could replace any single component with an alternative — Suricata for Zeek, Logstash for Filebeat, NATS for Kafka, Go for Python, Elasticsearch for OpenSearch — and the architecture wouldn't really change. The **shape** matters more than the specific tools.

---

## 3. The full pipeline diagram

```
                  +-------------------+
                  |  Network traffic  |
                  |  (PCAP or live)   |
                  +---------+---------+
                            |
                            v
        +-------------------+-------------------+
        |  Zeek                                 |
        |  - Parses every packet                |
        |  - Identifies protocol (TCP/UDP/...)  |
        |  - Generates conn.log/dns.log/...     |
        |  - Writes JSON to /logs (rotates 60s) |
        +-------------------+-------------------+
                            |
                            | (file system: zeek/logs/*.log)
                            v
        +-------------------+-------------------+
        |  Filebeat                             |
        |  - Tails each *.log file              |
        |  - Parses ndjson lines                |
        |  - Adds log_type field                |
        |  - Drops noisy fields                 |
        |  - Publishes to Kafka topic           |
        +-------------------+-------------------+
                            |
                            | (Kafka topics: zeek-conn, zeek-dns, zeek-http)
                            v
        +-------------------+-------------------+
        |  Kafka                                |
        |  - 3 partitions per topic             |
        |  - 24h retention                      |
        |  - Buffers events for the processor   |
        +-------------------+-------------------+
                            |
                            | (Kafka consumer groups: netwatch-processor-{conn,dns,http})
                            v
        +-------------------+-------------------+
        |  Python Processor (FastAPI)           |
        |                                       |
        |  ConnConsumer / DnsConsumer / HttpConsumer
        |    1. Validate with Pydantic          |
        |    2. Enrich (ip_classification)      |
        |    3. Detect (high_volume, port_scan, |
        |         dns_tunneling)                |
        |    4. Buffer for bulk indexing        |
        |                                       |
        |  Detectors fire alerts back to Kafka  |
        |  (zeek-alerts) AND into OpenSearch    |
        +-------------------+-------------------+
                |                       |
                | (bulk index)          | (alert publish)
                v                       v
        +-------+-------+       +-------+-------+
        | OpenSearch    |       | zeek-alerts   |
        | netwatch-conn |       | (Kafka topic) |
        | netwatch-dns  |       +---------------+
        | netwatch-http |
        | netwatch-alerts
        +-------+-------+
                |
                | (queries)
                v
        +-------+-------+        +----------------------+
        | Grafana       |        | OpenSearch Dashboards|
        | dashboards +  |        | (raw Discover view)  |
        | alert rules   |        +----------------------+
        +-------+-------+
                |
                v
        +-------+-------+
        | React UI      | ----> talks to FastAPI control plane (/api/*)
        | (Operator)    |
        +---------------+

                            ---

        +---------------------------------------+
        |  OpenTelemetry Collector              |
        |  - Scrapes processor /metrics         |
        |  - Re-exposes for Grafana             |
        +---------------------------------------+
```

---

## 4. Following one packet through the system

Let's trace a single TCP connection from your laptop to a web server through every stage of NetWatch.

### Stage 0: The packet exists

Your browser opens a TCP connection from `192.168.1.50:54321` to `93.184.216.34:443` (example.com). The connection lasts 2.3 seconds and exchanges 8 KB.

In a live capture this packet goes through your network interface; in PCAP replay mode (what `make pcap-demo` sets up) Zeek reads it from a `.pcap` file instead. From here on the path is identical.

### Stage 1: Zeek parses it

Zeek's TCP analyzer identifies the connection's start and end, and just before flushing it produces a JSON line in `/logs/conn.log`:

```json
{
  "ts": 1698000123.456,
  "uid": "C8gXyZ4abc",
  "id.orig_h": "192.168.1.50",
  "id.orig_p": 54321,
  "id.resp_h": "93.184.216.34",
  "id.resp_p": 443,
  "proto": "tcp",
  "service": "ssl",
  "duration": 2.34,
  "orig_bytes": 1024,
  "resp_bytes": 7168,
  "conn_state": "SF"
}
```

Zeek aggregates packets into **flows** — one log line per *connection*, not one per packet. This is why one TCP session = one `conn.log` row, even though hundreds of packets crossed the wire.

Up to 60 seconds may pass before Zeek flushes this line to disk. The interval is set in [zeek/config/local.zeek](../zeek/config/local.zeek) as `Log::default_rotation_interval = 60 secs`.

### Stage 2: Filebeat tails the file

Filebeat is watching `/zeek/logs/conn.log`. Within 5 seconds (`scan_frequency: 5s`) it notices the new content, parses the line as ndjson, attaches `log_type: conn`, drops fields like `agent` and `ecs`, and publishes the line to the Kafka topic `zeek-conn`.

The configuration that drives all this lives in [filebeat/filebeat.yml](../filebeat/filebeat.yml). One filestream input per protocol, one Kafka output that routes by `log_type`.

### Stage 3: Kafka buffers it

Kafka receives the event and writes it to one of `zeek-conn`'s 3 partitions (chosen round-robin). It's now durable on Kafka's disk and will be retained for 24 hours.

If the Python processor were down right now, the event would just sit here. When the processor comes back online, it picks up from where it left off and the event is processed normally — that's the whole point of having Kafka in the middle.

You can peek at this message yourself:

```bash
docker exec netwatch-kafka kafka-console-consumer \
  --bootstrap-server kafka:9092 \
  --topic zeek-conn --from-beginning --max-messages 1 --timeout-ms 5000
```

### Stage 4: The Python processor consumes it

`ConnConsumer` (in [python-processor/consumers/conn_consumer.py](../python-processor/consumers/conn_consumer.py)) is a Kafka consumer in the consumer group `netwatch-processor-conn`. Its asyncio loop calls `Consumer.poll(0.5)`, gets the message, and:

1. **Decodes JSON** → `dict`.
2. **Validates with Pydantic** → `ConnEvent.model_validate(...)`. This catches malformed events and aliases Zeek field names (`id.orig_h` → `src_ip`).
3. **Enriches** → `classify_ip(src_ip)` returns `{"classification": "external", ...}` because `192.168.1.50` is private but `93.184.216.34` is public. The result is cached in an `lru_cache` so the next time we see the same IP we skip the lookup.
4. **Runs detectors:**
    - `HighVolumeDetector` — adds `now()` to a per-IP `deque`, evicts entries older than 60 seconds, and checks if the count exceeds the configured threshold. For one connection, no — but if you replay the same PCAP at high speed it'll trip.
    - `PortScanDetector` — tracks distinct destination ports per source IP over a 30-second window. One connection to one port doesn't trip it.
5. **Sends to OpenSearch buffer** — adds the enriched dict to an in-memory list. When the list hits 100 items (or 5 seconds elapse) it bulk-indexes to `netwatch-conn-2026.04.09`.
6. **Commits the Kafka offset** manually. If we crashed before this line, on restart we'd replay this message — that's why the indexing must be idempotent (and it is, because we use Zeek's `uid` as a doc ID).

### Stage 5: OpenSearch indexes it

OpenSearch receives the bulk request and stores the document in `netwatch-conn-2026.04.09`. The mapping was set ahead of time by [opensearch/index-templates.json](../opensearch/index-templates.json), so `src_ip` and `dst_ip` are typed as `ip` (which lets us do CIDR queries), `dst_port` as `integer`, etc.

Verify it landed:

```bash
curl -s "http://localhost:9200/netwatch-conn-*/_count"
# {"count":1, ...}
```

### Stage 6: Grafana queries it

Grafana's "NetWatch Overview" dashboard refreshes every 10 seconds. Each panel runs an OpenSearch query — for example, the *Top 10 Source IPs* panel runs a `terms` aggregation on `src_ip`. Within 10–15 seconds of the document landing, our `192.168.1.50` shows up in the bar gauge.

### Stage 7: The React UI shows the alert badge (if applicable)

If a detector had fired, an alert dict would have been published to the `zeek-alerts` Kafka topic AND added to the `netwatch-alerts` index. The React Overview page polls `/api/alerts` every 5 seconds and the sidebar badge increments.

### End-to-end timing

| Stage                          | Worst case |
|--------------------------------|------------|
| Zeek log rotation              | 60 s       |
| Filebeat scan + ship           | 5 s        |
| Kafka write + processor poll   | < 1 s      |
| Processor batch flush          | 5 s        |
| Grafana dashboard refresh      | 10 s       |
| **Total**                      | **~80 s**  |

This is why the very first `make up` followed immediately by opening Grafana shows nothing — be patient.

---

## 5. Component deep dives

### 5.1 Zeek

**What it is:** A network security monitor (NSM) that turns packets into protocol-aware structured logs.

**Key idea:** Zeek doesn't do "alerting" the way Suricata does. It produces *facts* about traffic. The interpretation (alert/no alert) is the job of downstream systems — in our case, the Python processor.

**Files we wrote:**
- [zeek/Dockerfile](../zeek/Dockerfile) — based on `zeek/zeek:lts`, runs as non-root.
- [zeek/config/local.zeek](../zeek/config/local.zeek) — enables JSON output, sets rotation interval.
- [zeek/entrypoint.sh](../zeek/entrypoint.sh) — replays `capture.pcap` if present, else live captures.

**Output:** `conn.log`, `dns.log`, `http.log`, `ssl.log`, plus rotated copies (`*.YYYY-MM-DD-HH-MM-SS.log`).

**Common gotchas:** PCAP file must exist *before* the container starts (entrypoint only checks once). Logs only appear after the rotation interval — be patient. Older PCAPs have old timestamps, which trips up Grafana time ranges.

### 5.2 Filebeat

**What it is:** A lightweight log shipper from Elastic. It tails files, applies basic transformations, and ships them somewhere.

**Key idea:** Filebeat is *boring* and that's the point. We don't want our pipeline's "ingest" stage to also be a place where we add features — it should be a dumb pipe.

**Files we wrote:**
- [filebeat/filebeat.yml](../filebeat/filebeat.yml) — three filestream inputs (one per Zeek log type), Kafka output that routes by `log_type`.

**Common gotchas:** Filebeat tracks per-file offsets; once it's read a rotated log file end-to-end, it won't re-read it. To force re-reads in dev, `docker compose down -v filebeat`.

### 5.3 Kafka

**What it is:** A distributed log (pub/sub on steroids). Producers write to topics; consumers read from them at their own pace.

**Why we use it:**
- **Buffering** — if the processor crashes, events queue up here and aren't lost.
- **Replay** — we can rewind a consumer group to re-process old events.
- **Parallelism** — topics are partitioned (3 each here), so multiple consumers can read in parallel.

**Files we wrote:**
- Topic creation: [kafka/create-topics.sh](../kafka/create-topics.sh)
- Topic README: [kafka/README.md](../kafka/README.md)

**The four topics:**

| Topic         | Producer  | Consumer       | Why                              |
|---------------|-----------|----------------|----------------------------------|
| `zeek-conn`   | Filebeat  | ConnConsumer   | TCP/UDP connections              |
| `zeek-dns`    | Filebeat  | DnsConsumer    | DNS queries and responses        |
| `zeek-http`   | Filebeat  | HttpConsumer   | HTTP requests                    |
| `zeek-alerts` | Processor | (any)          | Anomaly alerts from detectors    |

**Common gotchas:** `KAFKA_BOOTSTRAP_SERVERS=kafka:9092` is the *internal* listener (containers talk to each other). If you wanted to connect from the host, you'd use `localhost:9092`.

### 5.4 Python processor (FastAPI)

**What it is:** The brain of the pipeline. It consumes Kafka, enriches each event, runs detection, and writes to OpenSearch. It also exposes a REST API for the React UI.

**Layered structure:**

| Layer       | Files                                 | Purpose                          |
|-------------|---------------------------------------|----------------------------------|
| Models      | `models/*.py`                         | Pydantic schemas for each Zeek log type. Validation + field aliasing. |
| Consumers   | `consumers/*.py`                      | Kafka consumer per topic. Owns the processing loop. |
| Enrichers   | `enrichers/*.py`                      | Decorate events with derived fields (`ip_classification`). |
| Detectors   | `detectors/*.py`                      | Stateful logic that decides whether to fire an alert. |
| Exporters   | `exporters/*.py`                      | Sinks: OpenSearch bulk indexer, Prometheus metrics. |
| API         | `api/routers/*.py`                    | FastAPI HTTP routes for the React UI. |
| Lifecycle   | `main.py`                             | Wires consumers, exporters, and HTTP routes together with `lifespan`. |

**Key patterns:**
- **Async everything.** Consumers run as asyncio tasks. The HTTP server and the Kafka consumers share one event loop.
- **Manual offset commit.** Auto-commit is disabled. Each event is only marked as processed *after* enrichment + detection + export succeed.
- **Dead-letter on failure.** If processing fails 3 times in a row, the event is published to `zeek-alerts` with `alert_type: processing_error` and the offset is committed past it. One bad message can't block the pipeline.
- **In-process sliding windows for detectors.** This is fine for one processor instance. For HA you'd move state to Redis.

### 5.5 OpenSearch

**What it is:** A distributed search engine. Open-source fork of Elasticsearch.

**Key idea:** OpenSearch is a *document store* + *inverted index* + *aggregation engine*. We use the aggregation engine for things like "top 10 source IPs" and "request rate per minute".

**Index naming convention:**

| Pattern                       | Contents                          |
|-------------------------------|-----------------------------------|
| `netwatch-conn-YYYY.MM.DD`    | One day of conn events            |
| `netwatch-dns-YYYY.MM.DD`     | One day of DNS events             |
| `netwatch-http-YYYY.MM.DD`    | One day of HTTP events            |
| `netwatch-alerts`             | All alerts (single index, 7d ISM) |

Date-stamping makes retention easy: drop yesterday's index to free space.

**Mappings are strict** (`"dynamic": "strict"`) so a typo in a field name is a hard error, not a silent schema drift. The mappings live in [opensearch/index-templates.json](../opensearch/index-templates.json).

### 5.6 OpenTelemetry Collector

**What it is:** A vendor-neutral pipeline for telemetry data — metrics, traces, logs *about* services.

**Why it's separate from the event pipeline:** The event pipeline (Zeek → Kafka → processor → OpenSearch) carries data *about the network*. The OTEL pipeline carries data *about the platform itself* — how many events the processor handled, how long enrichment took, whether OpenSearch is rejecting writes.

**What it does in NetWatch:**
- Scrapes the Python processor's `/metrics` endpoint every 15 seconds
- Re-exposes those metrics on its own `:8889/metrics` endpoint
- Forwards anything received via OTLP (gRPC 4317 / HTTP 4318) to OpenSearch

Configuration: [otel/config.yaml](../otel/config.yaml).

### 5.7 Grafana

**What it is:** A dashboard and alerting tool that pulls data from many backends (OpenSearch, Prometheus, etc.).

**What we ship:**
- Datasources auto-provisioned via [grafana/provisioning/datasources/opensearch.yaml](../grafana/provisioning/datasources/opensearch.yaml)
- One dashboard with 8 panels — [grafana/provisioning/dashboards/netwatch-overview.json](../grafana/provisioning/dashboards/netwatch-overview.json)
- Three alert rules — [grafana/provisioning/alerting/rules.yaml](../grafana/provisioning/alerting/rules.yaml)

**Default login:** `admin` / `admin` (change-on-first-login can be skipped in dev).

### 5.8 React frontend

**What it is:** A small operator dashboard built with Vite + TypeScript + Tailwind.

**Pages:**
- `/` — Overview, summary cards, recent alert feed
- `/alerts` — Filterable alert table
- `/explorer` — Free-form Lucene search over OpenSearch (via the FastAPI `/api/search`)
- `/settings` — Tune the alert threshold, pause/resume consumers

**Key files:**
- [frontend/src/lib/api.ts](../frontend/src/lib/api.ts) — Axios client, typed responses
- [frontend/src/stores/pipelineStore.ts](../frontend/src/stores/pipelineStore.ts) — Zustand store for global state (alert badge, pipeline health)
- [frontend/src/App.tsx](../frontend/src/App.tsx) — Routes
- [frontend/src/components/Layout.tsx](../frontend/src/components/Layout.tsx) — Sidebar + content shell

### 5.9 Postgres

**What it is:** Reserved for stateful control-plane data. **Not used yet.** Future home for:
- Persisted threshold overrides (so `/api/config` PATCH survives a restart)
- Audit log of who paused which consumer when
- User accounts if we add auth

---

## 6. Where each config lives

| Concern                          | File                                                                                 |
|----------------------------------|--------------------------------------------------------------------------------------|
| Service orchestration            | [docker-compose.yml](../docker-compose.yml)                                          |
| Environment variables            | [.env.example](../.env.example) → copy to `.env`                                     |
| Zeek policy / rotation interval  | [zeek/config/local.zeek](../zeek/config/local.zeek)                                  |
| Zeek live vs PCAP mode           | [zeek/entrypoint.sh](../zeek/entrypoint.sh)                                          |
| Filebeat → Kafka routing         | [filebeat/filebeat.yml](../filebeat/filebeat.yml)                                    |
| Kafka topic creation             | [kafka/create-topics.sh](../kafka/create-topics.sh)                                  |
| Processor settings (env-driven)  | [python-processor/config.py](../python-processor/config.py)                          |
| OpenSearch mappings              | [opensearch/index-templates.json](../opensearch/index-templates.json)                |
| OpenSearch bootstrap             | [opensearch/create-indices.sh](../opensearch/create-indices.sh)                      |
| OTEL pipeline                    | [otel/config.yaml](../otel/config.yaml)                                              |
| Grafana datasources              | [grafana/provisioning/datasources/opensearch.yaml](../grafana/provisioning/datasources/opensearch.yaml) |
| Grafana dashboards               | [grafana/provisioning/dashboards/netwatch-overview.json](../grafana/provisioning/dashboards/netwatch-overview.json) |
| Grafana alert rules              | [grafana/provisioning/alerting/rules.yaml](../grafana/provisioning/alerting/rules.yaml) |
| Frontend env (API URL)           | `.env` `VITE_API_BASE_URL`                                                           |

---

## 7. Hands-on exercises

Working through these will cement what you've read.

### Exercise 1: Watch one event traverse the whole pipeline

1. `make up && make pcap-demo`
2. Wait 90 seconds.
3. `tail zeek/logs/conn.log` — see one JSON line.
4. `docker exec netwatch-kafka kafka-console-consumer --bootstrap-server kafka:9092 --topic zeek-conn --from-beginning --max-messages 1 --timeout-ms 5000` — see the same data in Kafka.
5. `curl -s "http://localhost:9200/netwatch-conn-*/_search?size=1&pretty"` — see the **enriched** version (note `ip_classification` was added).
6. Open Grafana, set the time range to "Last 20 years", confirm panels populate.

You just watched data flow through five stages.

### Exercise 2: Fire a synthetic alert

```bash
curl -X POST http://localhost:8000/api/webhooks/alert \
  -H 'content-type: application/json' \
  -d '{"alert_type":"manual_test","severity":"high","src_ip":"10.0.0.99","ts": 0}'
```

Now check:
- `curl -s http://localhost:8000/api/alerts | jq` — should include your alert
- React UI Overview page — alert count should increment within 5 seconds
- Grafana "Active Alerts" panel — your alert appears (within 10s after refresh)

### Exercise 3: Lower the detection threshold to trigger a real alert

1. Edit `.env`: change `ALERT_THRESHOLD_REQUESTS_PER_MINUTE=1000` to `=5`.
2. `docker compose restart python-processor`
3. `make pcap-demo` (the replay will quickly exceed 5/minute for at least one IP)
4. After ~30 seconds: `curl -s http://localhost:8000/api/alerts | jq`

You should see real `high_volume` alerts from the IPs in the PCAP.

### Exercise 4: Add a new field to enrichment

1. Open [python-processor/consumers/conn_consumer.py](../python-processor/consumers/conn_consumer.py).
2. After the `doc["ip_classification"] = ...` line, add:
   ```python
   doc["is_internal"] = doc["ip_classification"] == "internal"
   ```
3. **Important:** Open [opensearch/index-templates.json](../opensearch/index-templates.json), find the `netwatch-conn` template, and add `"is_internal": { "type": "boolean" }` to the properties block. Without this, the strict mapping will reject your new field.
4. Re-apply the template: `docker exec netwatch-opensearch curl -X PUT "localhost:9200/_index_template/netwatch-conn" -H "content-type: application/json" -d @/path/to/your/template.json` — or simpler, `docker compose exec opensearch bash /opensearch/create-indices.sh`.
5. `docker compose restart python-processor`
6. After ~60 seconds, query OpenSearch and verify `is_internal` shows up on new docs.

### Exercise 5: Pause a consumer from the React UI

1. Open <http://localhost:3000/settings>
2. Click "Pause" next to `zeek-conn`
3. Verify with `curl -s http://localhost:8000/api/stats | jq '.consumers'` — `paused: true`
4. Watch `netwatch-conn-*` doc count stop growing in OpenSearch
5. Click "Resume"
6. Watch it start growing again

This shows the round-trip from React → FastAPI → consumer state → Kafka offsets.

---

## 8. Debugging by symptom

### "Grafana panels are empty"

Walk this exact order:

1. **`make pcap-demo` — was it run?** No PCAP = no data. Period.
2. **`ls zeek/logs/`** — any files? If not, Zeek is broken or in live-capture mode.
3. **`docker logs netwatch-zeek --tail 30`** — does it say `[zeek] replaying /pcap/capture.pcap`? If it says `[zeek] no capture.pcap — running live capture` and you have a PCAP on disk, restart Zeek: `docker compose restart zeek`.
4. **`docker logs netwatch-filebeat --tail 30`** — any errors? Look for Kafka connection failures.
5. **`docker exec netwatch-kafka kafka-topics --bootstrap-server kafka:9092 --list`** — do you see the four topics?
6. **`curl -s "http://localhost:9200/_cat/indices/netwatch-*?v"`** — any indices? `docs.count` > 0?
7. **`curl -s http://localhost:8000/api/stats`** — are events_processed_total counters > 0?
8. **Grafana time range** — set to "Last 20 years" if your PCAP is old.

### "I see Zeek logs on disk but Kafka is empty"

Filebeat is broken. `docker logs netwatch-filebeat`. Most likely cause: Kafka wasn't healthy when Filebeat started. Fix: `docker compose restart filebeat`.

### "Kafka has messages but OpenSearch is empty"

Processor is broken. `docker logs netwatch-processor`. Look for Pydantic validation errors, OpenSearch connection errors, or Python exceptions. Healthy log lines are JSON-formatted (`structlog`); errors are JSON too with `level: error`.

### "OpenSearch has docs but Grafana shows 'No Data'"

99% of the time: **wrong time range**. Click the time picker top-right and pick "Last 20 years" or whatever covers your PCAP's timestamps.

If the time range is right and OpenSearch Dashboards (<http://localhost:5601>) Discover view also shows nothing: the index pattern is wrong. Make sure the dashboard targets `netwatch-conn-*` (not `netwatch-conn`).

### "I see `/opt/zeek/bin/zeek: No such file or directory`"

Old bug, fixed in this repo. The upstream image puts `zeek` on `PATH` but not at `/opt/zeek/bin`. The entrypoint now calls `zeek` by name. If you're running an old build, `docker compose up -d --build zeek`.

### "tail: cannot open 'C:/Tools/Git/logs/conn.log'"

Git Bash on Windows is mangling your paths. Use `//logs/conn.log` (double slash) or `MSYS_NO_PATHCONV=1`. Or just read the host file: `tail zeek/logs/conn.log`.

### "make: \*\*\* [Makefile:NN] Error 1" on Windows

You're running `make` from `cmd.exe` or PowerShell. Open **Git Bash** and try again.

### "OpenSearch is restarting in a loop"

Out of memory. Bump Docker Desktop to 6+ GB in *Settings → Resources*.

---

## 9. Vocabulary you should know

| Term | Meaning |
|---|---|
| **NSM** | Network Security Monitoring. The general practice Zeek belongs to. |
| **PCAP** | Packet Capture file. A binary recording of network packets, typically `.pcap` or `.pcapng`. |
| **Flow** | A logical unit of network communication — a TCP connection, a UDP exchange. Zeek's `conn.log` is one row per flow. |
| **Topic (Kafka)** | A named stream of messages. Producers write to it; consumers read from it. Like a durable, ordered queue. |
| **Partition (Kafka)** | A topic is split into N partitions for parallelism. Each partition is an ordered log; ordering across partitions is not guaranteed. |
| **Consumer group (Kafka)** | A label that lets multiple consumer instances share work on a topic. Each partition is read by exactly one consumer in the group. |
| **Offset (Kafka)** | A position in a partition. The consumer's "bookmark". |
| **Index (OpenSearch)** | A named collection of documents with a schema (mapping). Roughly equivalent to a database table. |
| **Document (OpenSearch)** | A JSON object stored in an index. Roughly equivalent to a database row. |
| **Mapping (OpenSearch)** | The schema for an index — what fields exist, what type each one is. |
| **Index template** | A mapping that gets applied automatically to any new index matching a name pattern. |
| **Lucene query** | The query language OpenSearch (and Elasticsearch) supports natively. Example: `src_ip:10.0.0.0/8 AND status_code:500`. |
| **Datasource (Grafana)** | A configured connection to a data backend (OpenSearch, Prometheus, etc.). |
| **Provisioning (Grafana)** | Loading datasources and dashboards from YAML/JSON files at startup, instead of clicking through the UI. |
| **Sliding window (detector)** | A counter or set that only retains entries from the last N seconds. Used for "X events in the last minute" rules. |
| **Bulk indexing** | Sending many OpenSearch index requests in one HTTP call. Much faster than one-at-a-time. |
| **OTLP** | OpenTelemetry Protocol. The wire format OTEL services use to talk to each other. |
| **ISM** | Index State Management. OpenSearch's lifecycle policy system (e.g., "delete indices older than 7 days"). |
| **DLQ / dead-letter** | A place to send messages that failed processing too many times, so they don't block the pipeline. |

---

## 10. Where to read next

- [README.md](../README.md) — quick start, validation steps, troubleshooting.
- [docs/ARCHITECTURE.md](ARCHITECTURE.md) — deeper architecture rationale and scaling story.
- [docs/INTERVIEW_GUIDE.md](INTERVIEW_GUIDE.md) — talking points for explaining the project.
- **Zeek docs:** <https://docs.zeek.org/>
- **Kafka concepts:** <https://kafka.apache.org/intro>
- **OpenSearch query DSL:** <https://opensearch.org/docs/latest/query-dsl/>
- **FastAPI tutorial:** <https://fastapi.tiangolo.com/tutorial/>
- **Grafana provisioning:** <https://grafana.com/docs/grafana/latest/administration/provisioning/>

If you've read everything here you understand NetWatch end to end. Welcome to the team.
