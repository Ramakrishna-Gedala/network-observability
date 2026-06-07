# NetWatch Python Processor

The central brain of the NetWatch pipeline. This service reads raw Zeek network logs from Kafka, validates and normalizes them through Pydantic models, enriches each event (e.g., IP classification), runs anomaly detectors (port scan, high volume, DNS tunneling), bulk-indexes everything into OpenSearch, and exposes a REST API for the React operator UI.

## Architecture overview

```
                      +-------------------+
                      |      Kafka        |
                      |  (3 topics)       |
                      +---------+---------+
                                |
              +-----------------+-----------------+
              |                 |                 |
     zeek-conn topic    zeek-dns topic    zeek-http topic
              |                 |                 |
      +-------v------+  +------v-------+  +------v-------+
      | ConnConsumer  |  | DnsConsumer  |  | HttpConsumer |
      +-------+------+  +------+-------+  +------+-------+
              |                 |                 |
              |  Each consumer runs this 4-step pipeline:
              |
              |   1. PARSE      --  Pydantic model validates raw JSON
              |   2. ENRICH     --  IP classifier tags internal/external
              |   3. DETECT     --  Anomaly detectors fire alerts
              |   4. EXPORT     --  Buffered bulk-index to OpenSearch
              |
              +-----------------+-----------------+
                                |
                   +------------v-----------+
                   |   OpenSearch Exporter  |
                   |   (async bulk, batched)|
                   +------------+-----------+
                                |
              +-----------------+-----------------+
              |                 |                 |
     netwatch-conn-*   netwatch-dns-*   netwatch-http-*
              |
     netwatch-alerts  (flat, not date-stamped)
```

Alongside the consumers, a **FastAPI** HTTP server runs in the same process, sharing the asyncio event loop. This API serves the React frontend and the Grafana alert webhooks.

## Directory structure

```
python-processor/
  main.py                      # FastAPI app + lifespan (starts consumers as asyncio tasks)
  config.py                    # Pydantic Settings -- reads env vars / .env file
  Dockerfile                   # Python 3.11-slim, librdkafka, runs as non-root
  requirements.txt             # Pinned dependencies

  models/                      # Pydantic v2 models for Zeek log types
    conn_event.py              # ConnEvent  -- conn.log fields
    dns_event.py               # DnsEvent   -- dns.log fields
    http_event.py              # HttpEvent  -- http.log fields

  consumers/                   # Kafka consumers (one per Zeek log type)
    base_consumer.py           # Abstract async consumer with retry + dead-letter
    conn_consumer.py           # zeek-conn topic: enrich + detect + export
    dns_consumer.py            # zeek-dns  topic: enrich + detect + export
    http_consumer.py           # zeek-http topic: enrich + detect + export

  enrichers/                   # Event enrichment plugins
    ip_enricher.py             # Classifies IPs as internal/external/loopback/reserved
    geo_enricher.py            # GeoIP stub (placeholder for MaxMind integration)

  detectors/                   # Anomaly detection engines
    base_detector.py           # Abstract detector interface
    high_volume.py             # Sliding-window per-IP rate detector
    port_scan.py               # Horizontal port-scan detector (distinct ports/window)
    dns_tunneling.py           # Long-query / deep-subdomain heuristic
    alert_publisher.py         # Publishes alerts to the zeek-alerts Kafka topic

  exporters/                   # Output sinks
    opensearch_exporter.py     # Async bulk indexer with in-memory buffer
    otel_exporter.py           # Prometheus counters/histograms for /metrics

  api/                         # FastAPI HTTP API
    dependencies.py            # Dependency injection (exporter, consumers, publisher)
    routers/
      health.py                # GET  /health
      stats.py                 # GET  /api/stats
      alerts.py                # GET  /api/alerts, POST /api/webhooks/alert
      search.py                # GET  /api/search
      config.py                # GET  /api/config, PATCH /api/config
      consumers.py             # POST /api/consumers/{topic}/pause|resume
```

## How it starts (main.py lifespan)

When `uvicorn main:app` boots:

1. **Settings load** -- `config.py` reads env vars (`KAFKA_BOOTSTRAP_SERVERS`, `OPENSEARCH_URL`, etc.) using Pydantic Settings. Falls back to defaults for local dev.

2. **Singletons created** -- An `OpenSearchExporter` (async bulk client) and an `AlertPublisher` (Kafka producer for `zeek-alerts`) are instantiated once and shared across all consumers.

3. **Consumer tasks launched** -- Three `asyncio.Task`s are created, one each for `ConnConsumer`, `DnsConsumer`, and `HttpConsumer`. Each consumer subscribes to its Kafka topic and enters an infinite poll loop.

4. **Periodic flusher** -- A fourth task calls `exporter.flush()` every 5 seconds, ensuring buffered events reach OpenSearch even if the batch-size threshold (100) hasn't been hit.

5. **FastAPI ready** -- The HTTP server starts accepting requests. CORS is configured for the frontend origin (`http://localhost:3000` by default).

6. **Shutdown** -- On SIGTERM/SIGINT: all consumers are stopped, tasks cancelled, the alert publisher is flushed, and the OpenSearch client is closed.

## Consumers -- the core processing loop

### BaseConsumer (base_consumer.py)

Every consumer inherits from `BaseConsumer`, which provides:

- **Kafka polling** -- `confluent_kafka.Consumer.poll(0.5)` runs inside `loop.run_in_executor()` so the blocking C call does not freeze the asyncio event loop (this is critical -- without it, FastAPI cannot serve HTTP requests).
- **Manual offset commits** -- `enable.auto.commit = False`. Offsets are committed only after a message is fully processed and exported.
- **Retry with dead-letter** -- If `process()` throws, it retries up to 3 times with exponential backoff (0.5s, 1s, 1.5s). After 3 failures, the event is published to `zeek-alerts` as a `processing_error` alert and the offset is committed (so processing moves forward).
- **Pause/resume** -- The operator UI can pause a consumer via the API. When paused, the poll loop sleeps instead of polling.
- **auto.offset.reset = "earliest"** -- New consumer groups start from the beginning of the topic, so events that Filebeat shipped before the processor started are not lost.

### Per-topic consumers

Each consumer's `process()` method runs the 4-step pipeline:

#### ConnConsumer (zeek-conn)
```
Raw JSON -> ConnEvent.model_validate() -> classify_ip(src_ip) -> HighVolumeDetector + PortScanDetector -> exporter.add("conn", doc)
```

#### DnsConsumer (zeek-dns)
```
Raw JSON -> DnsEvent.model_validate() -> classify_ip(src_ip) -> DnsTunnelingDetector -> exporter.add("dns", doc)
```

#### HttpConsumer (zeek-http)
```
Raw JSON -> HttpEvent.model_validate() -> classify_ip(src_ip) -> HighVolumeDetector -> exporter.add("http", doc)
```

When a detector fires, the alert is:
1. Published to the `zeek-alerts` Kafka topic (via `AlertPublisher`)
2. Recorded as a Prometheus counter (`alerts_emitted_total`)
3. Indexed into the `netwatch-alerts` OpenSearch index
4. Attached to the source event as `alert_type` before indexing

## Models (Pydantic v2)

Zeek uses unusual field names like `id.orig_h` (source IP) and `orig_bytes`. Pydantic Field aliases handle the mapping:

```python
class ConnEvent(BaseModel):
    model_config = ConfigDict(extra="allow")   # don't reject unknown Zeek fields

    src_ip: str | None = Field(None, alias="id.orig_h")
    dst_ip: str | None = Field(None, alias="id.resp_h")
    bytes_sent: int | None = Field(None, alias="orig_bytes")
    # ...
```

`extra="allow"` is important -- Zeek outputs many fields that we don't explicitly model (e.g., `local_orig`, `missed_bytes`). With `extra="forbid"` or `extra="ignore"`, these would either raise validation errors or be silently dropped. `extra="allow"` keeps them in the model so they pass through to OpenSearch (the index template has `"dynamic": false`, so unmapped fields are stored but not indexed).

## Enrichers

### IP Enricher (ip_enricher.py)

Classifies every `src_ip` into one of:
- **internal** -- matches configured CIDR ranges (default: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
- **external** -- public IP, not in any internal range
- **loopback** -- `127.x.x.x`
- **reserved** -- multicast, link-local, etc.
- **invalid** -- unparseable string

Results are memoized with `@lru_cache(maxsize=10_000)` so the same IP is only classified once.

### Geo Enricher (geo_enricher.py)

Stub/placeholder. Returns `None` for all fields. To enable real GeoIP:
1. Mount a MaxMind GeoLite2 database into the container
2. Replace the stub with a `geoip2.database.Reader` lookup

## Detectors

All detectors implement `BaseDetector.inspect(event) -> list[alert_dict]`. They return an empty list if no anomaly is detected.

### HighVolumeDetector

Tracks events per source IP in a sliding time window (default: 60 seconds). If the count exceeds the threshold (default: 1000/min), fires a `high_volume` alert. Has a 30-second cooldown per IP to avoid alert storms.

Used by: ConnConsumer, HttpConsumer.

### PortScanDetector

Tracks distinct destination ports per source IP in a 30-second window. If an IP touches 20+ distinct ports, fires a `port_scan` alert. Has a 60-second cooldown.

Used by: ConnConsumer only.

### DnsTunnelingDetector

Stateless heuristic: if a DNS query name is longer than 50 characters OR has more than 4 subdomain levels, flags it as `dns_tunneling_suspect`. This catches the common pattern of encoding data in subdomain labels (e.g., `aGVsbG8=.data.evil.com`).

Used by: DnsConsumer only.

### AlertPublisher

Not a detector, but lives in the `detectors/` package. A Kafka `Producer` that writes alert dicts to the `zeek-alerts` topic with:
- Idempotent delivery (`enable.idempotence: true`)
- Full acknowledgment (`acks: all`)
- gzip compression

## Exporters

### OpenSearchExporter (opensearch_exporter.py)

- Uses `AsyncOpenSearch` (requires `aiohttp` as a transport)
- Maintains an in-memory buffer per log type
- When the buffer hits 100 events OR the periodic flusher fires (every 5s), calls `opensearch.helpers.async_bulk()` to index the batch
- Index naming:
  - `netwatch-conn-2024.01.15` (date-stamped, one per day)
  - `netwatch-dns-2024.01.15`
  - `netwatch-http-2024.01.15`
  - `netwatch-alerts` (flat, not date-stamped)

### OtelExporter (otel_exporter.py)

Wraps Prometheus client counters and histograms:
- `events_processed_total` (labels: topic, status) -- tracks ok, bad_json, dead_letter
- `alerts_emitted_total` (labels: alert_type, severity)
- `event_processing_latency_seconds` (histogram, per topic)

These metrics are exposed at `GET /metrics` by `prometheus-fastapi-instrumentator` and scraped by the OpenTelemetry Collector.

## REST API

All endpoints are prefixed with `/api` (except `/health` and `/metrics`).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe -- returns `{"status": "ok"}` |
| GET | `/metrics` | Prometheus metrics (scrape target) |
| GET | `/api/stats` | Per-topic event counts + consumer running/paused state |
| GET | `/api/alerts?limit=50` | Recent alerts from the `netwatch-alerts` index |
| POST | `/api/webhooks/alert` | Ingest an external alert; optionally forwards to Slack |
| GET | `/api/search?q=*&index=conn&size=50&offset=0` | Lucene query pass-through to OpenSearch |
| GET | `/api/config` | Current runtime config (thresholds, CIDR ranges) |
| PATCH | `/api/config` | Live-tune `alert_threshold_requests_per_minute` |
| POST | `/api/consumers/{topic}/pause` | Pause a consumer (stops polling) |
| POST | `/api/consumers/{topic}/resume` | Resume a paused consumer |

### Search API example

```bash
# Find all HTTP events to a specific host
curl 'http://localhost:8000/api/search?q=host:evil.com&index=http&size=10'

# Find all connection events from a source IP
curl 'http://localhost:8000/api/search?q=src_ip:192.168.1.100&index=conn'

# Get all alerts
curl 'http://localhost:8000/api/search?q=*&index=alerts'
```

### Live config tuning

```bash
# Check current threshold
curl http://localhost:8000/api/config

# Lower the high-volume alert threshold to 100 events/minute
curl -X PATCH http://localhost:8000/api/config \
  -H 'Content-Type: application/json' \
  -d '{"alert_threshold_requests_per_minute": 100}'
```

Changes are in-memory only. Restarting the processor reverts to the env var value.

### Consumer control

```bash
# Pause the conn consumer (stops polling Kafka)
curl -X POST http://localhost:8000/api/consumers/zeek-conn/pause

# Resume it
curl -X POST http://localhost:8000/api/consumers/zeek-conn/resume
```

## Configuration (environment variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | Kafka broker address |
| `OPENSEARCH_URL` | `http://opensearch:9200` | OpenSearch cluster URL |
| `OPENSEARCH_INDEX_PREFIX` | `netwatch` | Prefix for all index names |
| `INTERNAL_CIDR_RANGES` | `10.0.0.0/8,172.16.0.0/12,192.168.0.0/16` | Comma-separated CIDRs for IP classification |
| `ALERT_THRESHOLD_REQUESTS_PER_MINUTE` | `1000` | High-volume detector threshold |
| `POSTGRES_DSN` | `postgresql+asyncpg://netwatch:netwatch_dev@postgres:5432/netwatch` | PostgreSQL connection string |
| `SLACK_WEBHOOK_URL` | (empty) | Optional Slack webhook for alert forwarding |
| `CORS_ALLOW_ORIGINS` | `http://localhost:3000` | Allowed CORS origins (comma-separated) |

## Data flow: one event's journey

Here is what happens to a single Zeek `conn.log` entry from start to finish:

```
1. Zeek writes JSON to /logs/conn.log
   {"ts":1278472580.91,"uid":"C1234","id.orig_h":"192.168.1.5","id.resp_h":"8.8.8.8","id.resp_p":53,...}

2. Filebeat reads the line, adds log_type:"conn", ships to Kafka topic "zeek-conn"

3. ConnConsumer.poll() picks up the message from Kafka

4. PARSE: ConnEvent.model_validate(event)
   - "id.orig_h" mapped to src_ip via Field alias
   - "orig_bytes" mapped to bytes_sent
   - Unknown Zeek fields kept (extra="allow")

5. ENRICH: classify_ip("192.168.1.5")
   - Matches 192.168.0.0/16 -> ip_classification = "internal"

6. DETECT: HighVolumeDetector.inspect(doc) + PortScanDetector.inspect(doc)
   - If 192.168.1.5 has sent > 1000 events in the last 60s: fire alert
   - If 192.168.1.5 has touched > 20 distinct ports in 30s: fire alert
   - Most events: no alert fired, returns []

7. EXPORT: exporter.add("conn", doc)
   - Doc added to in-memory buffer
   - When buffer reaches 100 docs (or flush timer fires):
     opensearch.helpers.async_bulk() writes to "netwatch-conn-2024.01.15"

8. COMMIT: consumer.commit(msg)
   - Kafka offset committed so this message won't be reprocessed
```

## Key design decisions

- **Single process, shared event loop** -- Consumers and FastAPI share one Python process. This avoids IPC complexity and lets the API read consumer state directly (e.g., pause/resume, live stats). The trade-off is that blocking calls must be offloaded to threads via `run_in_executor()`.

- **Manual Kafka commits** -- Auto-commit risks losing events if the process crashes between commit and export. Manual commit-after-export guarantees at-least-once delivery.

- **Buffered bulk indexing** -- Sending one OpenSearch request per event would be too slow. The exporter buffers up to 100 docs and bulk-indexes them. A periodic flusher handles low-throughput periods where the batch threshold isn't reached.

- **In-process detectors** -- Detectors use in-memory sliding windows (deques, dicts) rather than external state stores. This is simple and fast, but state is lost on restart. For production, consider Redis-backed windows.

- **extra="allow" on models** -- Zeek adds/removes fields across versions. Strict validation would break on upgrades. We explicitly model the fields we care about and pass the rest through.

## Troubleshooting

**API endpoints timeout (10s) but /health works**
The Kafka `Consumer.poll()` is a blocking C call. If run directly in an `async def`, it freezes the event loop and blocks all HTTP requests. Fix: wrap `poll()` and `commit()` in `loop.run_in_executor()` (already done in `base_consumer.py`).

**Processor in restart loop -- ImportError: AsyncOpenSearch**
`opensearch-py` only exposes `AsyncOpenSearch` if `aiohttp` is installed. Check that `aiohttp` is in `requirements.txt`.

**No data in OpenSearch but consumers show "ok" in /api/stats**
The buffer hasn't flushed yet. Wait 5 seconds for the periodic flusher, or check the OpenSearch index directly:
```bash
curl 'http://localhost:9200/_cat/indices/netwatch-*?v'
```

**Consumer stuck at offset 0, no events processed**
Kafka topics might not exist yet. Ensure Filebeat has shipped at least one event:
```bash
docker exec netwatch-kafka kafka-topics --list --bootstrap-server localhost:9092
```

**Alerts not appearing**
The sample PCAP may not trigger detectors -- thresholds are tuned for production traffic volumes. Lower the threshold:
```bash
curl -X PATCH http://localhost:8000/api/config \
  -d '{"alert_threshold_requests_per_minute": 10}' \
  -H 'Content-Type: application/json'
```
