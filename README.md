# NetWatch — Full-Stack Network Observability Platform

NetWatch is an end-to-end, Dockerized network observability stack: Zeek captures traffic, Kafka buffers it, a Python/FastAPI processor enriches and scores every event, OpenSearch stores it, and Grafana + a React operator dashboard visualize it.

## Architecture

```
  +----------+     +----------+     +-------+     +-------------------+
  |  Zeek    | --> | Filebeat | --> | Kafka | --> |  Python Processor |
  |  (IDS)   |     |  (ship)  |     |       |     |  FastAPI+consumers|
  +----------+     +----------+     +-------+     +---------+---------+
       ^                                              |     |     |
       |                                              v     v     v
   pcap/iface                                   OpenSearch  OTEL  Postgres
                                                    |        |
                                                    v        v
                                                 Grafana  (metrics)
                                                    ^
                                                    |
                                             React Operator UI
                                             (via FastAPI /api)
```

## Prerequisites

- Docker 24+
- Docker Compose v2
- 8 GB RAM (OpenSearch + Grafana + Kafka are the heavy hitters)

## Quick start

```bash
git clone <repo-url> netwatch && cd netwatch
cp .env.example .env         # edit secrets if desired
make up                      # build and start everything
make topics                  # create Kafka topics
# (optional) drop a PCAP into zeek/pcap/capture.pcap and `docker compose restart zeek`
```

Then open:

| Service                | URL                           |
|------------------------|-------------------------------|
| React operator UI      | http://localhost:3000         |
| FastAPI / processor    | http://localhost:8000/docs    |
| Grafana                | http://localhost:3001         |
| OpenSearch Dashboards  | http://localhost:5601         |
| Kafka UI               | http://localhost:8090         |
| OpenSearch REST        | http://localhost:9200         |

## Port reference

| Port   | Service              |
|--------|----------------------|
| 3000   | Frontend (React)     |
| 3001   | Grafana              |
| 4317   | OTEL OTLP gRPC       |
| 4318   | OTEL OTLP HTTP       |
| 5432   | Postgres             |
| 5601   | OpenSearch Dashboards|
| 8000   | Python processor API |
| 8090   | Kafka UI             |
| 8889   | OTEL Prometheus      |
| 9092   | Kafka                |
| 9200   | OpenSearch REST      |

## Pipeline overview

1. **Zeek** watches a live interface (or replays `capture.pcap`) and produces `conn.log`, `dns.log`, `http.log`, `ssl.log` as JSON.
2. **Filebeat** tails those files and publishes each line to a per-protocol Kafka topic (`zeek-conn`, `zeek-dns`, `zeek-http`).
3. **Python processor** consumes each topic in its own consumer group, validates with Pydantic, enriches (`ip_classification`), runs detectors (high-volume, port-scan, DNS-tunneling), and bulk-indexes into date-stamped OpenSearch indices.
4. **Detectors** publish alerts back to `zeek-alerts` and into the `netwatch-alerts` OpenSearch index.
5. **Grafana** reads OpenSearch and Prometheus (via OTEL collector) to drive dashboards and alert rules.
6. **React dashboard** talks only to the FastAPI control plane (`/api/*`).

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the deep dive.

## Adding a new detector

1. Create a new class in [python-processor/detectors/](python-processor/detectors/) that inherits from [`BaseDetector`](python-processor/detectors/base_detector.py) and implements `inspect(event) -> list[dict]`.
2. Export it from [python-processor/detectors/__init__.py](python-processor/detectors/__init__.py).
3. Instantiate it inside the relevant consumer (e.g. [ConnConsumer](python-processor/consumers/conn_consumer.py)) and call it from `process()`.
4. Append its alerts to `self._alert_publisher.publish_alert(...)` — this keeps Grafana rules firing without extra plumbing.
5. Restart the processor: `docker compose restart python-processor`.

## Troubleshooting

1. **Zeek writes no logs.** No live traffic and no PCAP — drop a sample into `zeek/pcap/capture.pcap` and `docker compose restart zeek`.
2. **Kafka UI empty / Filebeat errors.** Make sure Kafka is healthy (`docker compose ps`) before starting Filebeat. `make reset` is the nuclear option.
3. **OpenSearch container OOMKilled.** Bump Docker's memory allocation to at least 4 GB; the container is pinned to `-Xms512m -Xmx512m` but the JVM needs headroom.
4. **`/api/alerts` returns empty.** The `netwatch-alerts` index is created on first write. Fire a test alert: `curl -X POST localhost:8000/api/webhooks/alert -H 'content-type: application/json' -d '{"alert_type":"test","severity":"high"}'`.
5. **Processor can't connect to Kafka.** Check that `KAFKA_BOOTSTRAP_SERVERS=kafka:9092` (the internal listener), not `localhost:9092`.
