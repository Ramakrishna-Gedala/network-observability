# grafana/

**What lives here:** Grafana provisioning — datasources, dashboard JSON, and alert rule YAML — all loaded automatically when the Grafana container starts.

**Why it exists:** Grafana is the primary visualization and alerting surface for the raw event stream. Provisioning everything as code makes dashboards reproducible across environments.

**How it connects to the next stage:** Reads from [../opensearch/](../opensearch/) (event indices) and the [../otel/](../otel/) collector (Prometheus-format metrics), and fires alerts that mirror those produced by the python-processor into the `zeek-alerts` topic.
