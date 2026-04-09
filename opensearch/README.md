# opensearch/

**What lives here:** Index templates and a bootstrap shell script that create the `netwatch-conn-*`, `netwatch-dns-*`, `netwatch-http-*`, and `netwatch-alerts` indices with strict mappings.

**Why it exists:** OpenSearch is the primary searchable store for enriched events and alerts. Defining templates up front prevents dynamic-mapping drift and keeps IP, port, and timestamp fields correctly typed for aggregations.

**How it connects to the next stage:** The python-processor writes to these indices, and [../grafana/](../grafana/) reads them back through the OpenSearch datasource for dashboards and alerts.
