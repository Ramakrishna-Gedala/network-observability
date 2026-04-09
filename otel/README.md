# otel/

**What lives here:** OpenTelemetry Collector configuration (`config.yaml`) defining the receivers, processors, and exporters that unify logs, metrics, and traces across NetWatch services.

**Why it exists:** OTEL gives us a single, vendor-neutral plane for observability signals. The python-processor emits metrics via Prometheus and traces via OTLP; the collector normalizes and fans them out to OpenSearch and Grafana.

**How it connects to the next stage:** Scrapes `/metrics` from the python-processor and receives OTLP signals, then exports logs to [../opensearch/](../opensearch/) and metrics to [../grafana/](../grafana/) via a Prometheus-format endpoint.
