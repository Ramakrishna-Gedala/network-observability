# python-processor/

**What lives here:** The FastAPI service that consumes Kafka topics, enriches each event (IP classification, geo stub), runs anomaly detectors (high-volume, port-scan, DNS-tunneling), and exports to OpenSearch plus OTEL. It also exposes a control-plane HTTP API used by the React frontend.

**Why it exists:** This is the brain of the pipeline — the only place raw network events are turned into structured, enriched, alert-carrying documents. Keeping it in Python makes detectors easy to iterate on.

**How it connects to the next stage:** Consumes from Kafka (`zeek-*` topics), writes documents to [../opensearch/](../opensearch/) (indexed as `netwatch-conn-*`, `netwatch-dns-*`, `netwatch-http-*`, `netwatch-alerts`), emits metrics/traces to the [../otel/](../otel/) collector, and serves JSON over HTTP to the [../frontend/](../frontend/).
