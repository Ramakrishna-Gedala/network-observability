# kafka/

**What lives here:** Kafka topic creation scripts and producer/consumer configuration notes. The broker itself runs as a container defined in the root `docker-compose.yml`.

**Why it exists:** Kafka decouples the ingest side (Zeek + Filebeat) from the processing side (Python processor). This gives us buffering during processor restarts, replay for debugging, and per-topic parallelism.

**How it connects to the next stage:** Topics `zeek-conn`, `zeek-dns`, `zeek-http` are consumed by the Python processor. The processor publishes anomaly alerts back to `zeek-alerts`, which Grafana and the operator dashboard watch for notifications.

## Message flow

1. **Zeek** writes one JSON object per network event to disk (`conn.log`, `dns.log`, `http.log`).
2. **Filebeat** tails those files and publishes each line to a per-protocol topic, routing by the `log_type` field set in [../filebeat/filebeat.yml](../filebeat/filebeat.yml).
3. **Python processor** runs one consumer per topic, each in its own consumer group, in parallel asyncio tasks. Naming convention: `netwatch-processor-{log_type}` (e.g. `netwatch-processor-conn`). This lets us scale or pause topics independently.
4. **Anomaly alerts** produced by the detectors are re-published to the `zeek-alerts` topic. Grafana alert rules and the React dashboard subscribe to this topic (via OpenSearch) to surface alerts to operators.

## Topics

| Topic         | Partitions | Replication | Retention |
|---------------|------------|-------------|-----------|
| `zeek-conn`   | 3          | 1           | 24h       |
| `zeek-dns`    | 3          | 1           | 24h       |
| `zeek-http`   | 3          | 1           | 24h       |
| `zeek-alerts` | 1          | 1           | 7d        |

Run `make topics` (or exec `create-topics.sh` inside the Kafka container) to create them.
