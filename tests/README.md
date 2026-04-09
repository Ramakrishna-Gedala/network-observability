# NetWatch E2E Tests

These tests drive the full Docker-Compose stack and validate that the pipeline is flowing data end to end.

## Prerequisites

1. `make up` completed successfully — all containers healthy.
2. Sample PCAP in place so Zeek has something to chew on:
   - Download any PCAP from <https://wiki.wireshark.org/SampleCaptures> (e.g. `http.cap`, `dns.cap`).
   - Save it as `zeek/pcap/capture.pcap`.
   - `docker compose restart zeek`.
3. Python test deps: `pip install pytest httpx confluent-kafka`.

## Running

```bash
make test
# or
pytest tests/e2e/ -v
```

## Environment variables (optional)

| Variable         | Default                   | Purpose                                |
|------------------|---------------------------|----------------------------------------|
| `PROCESSOR_URL`  | `http://localhost:8000`   | FastAPI base URL                       |
| `OPENSEARCH_URL` | `http://localhost:9200`   | OpenSearch base URL                    |
| `GRAFANA_URL`    | `http://localhost:3001`   | Grafana base URL                       |
| `KAFKA_BOOTSTRAP`| `localhost:9092`          | Kafka bootstrap for the test consumer  |
| `GRAFANA_USER`   | (unset)                   | Enables `test_grafana_datasource`      |
| `GRAFANA_PASS`   | (unset)                   | Enables `test_grafana_datasource`      |
