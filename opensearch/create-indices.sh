#!/usr/bin/env bash
#
# Bootstrap OpenSearch index templates and the alerts index with a
# 7-day lifecycle policy. Intended to run once on startup (via `make up`
# or manually).
#
set -euo pipefail

OS_URL="${OPENSEARCH_URL:-http://opensearch:9200}"

echo "[opensearch] waiting for cluster at ${OS_URL}..."
until curl -fs "${OS_URL}/_cluster/health" > /dev/null; do
    sleep 2
done
echo "[opensearch] cluster is healthy"

TEMPLATES_JSON="$(dirname "$0")/index-templates.json"

apply_template () {
    local name="$1"
    local body
    body=$(python3 -c "import json,sys; print(json.dumps(json.load(open('${TEMPLATES_JSON}'))['${name}']))")
    echo "[opensearch] applying index template: ${name}"
    curl -fsS -X PUT "${OS_URL}/_index_template/${name}" \
        -H "Content-Type: application/json" \
        -d "${body}"
    echo
}

apply_template netwatch-conn
apply_template netwatch-dns
apply_template netwatch-http

echo "[opensearch] creating netwatch-alerts index"
curl -fsS -X PUT "${OS_URL}/netwatch-alerts" \
    -H "Content-Type: application/json" \
    -d '{
      "settings": { "number_of_shards": 1, "number_of_replicas": 0 },
      "mappings": {
        "dynamic": "true",
        "properties": {
          "ts": { "type": "date", "format": "epoch_second||strict_date_optional_time" },
          "alert_type": { "type": "keyword" },
          "src_ip": { "type": "ip" },
          "severity": { "type": "keyword" },
          "count": { "type": "long" },
          "window_seconds": { "type": "integer" }
        }
      }
    }' || true
echo

# 7-day ISM (Index State Management) policy for alerts
echo "[opensearch] applying 7-day ISM policy on netwatch-alerts"
curl -fsS -X PUT "${OS_URL}/_plugins/_ism/policies/netwatch-alerts-7d" \
    -H "Content-Type: application/json" \
    -d '{
      "policy": {
        "description": "Retain NetWatch alerts for 7 days",
        "default_state": "hot",
        "states": [
          {
            "name": "hot",
            "actions": [],
            "transitions": [ { "state_name": "delete", "conditions": { "min_index_age": "7d" } } ]
          },
          { "name": "delete", "actions": [ { "delete": {} } ], "transitions": [] }
        ],
        "ism_template": { "index_patterns": ["netwatch-alerts*"] }
      }
    }' || true
echo

echo "[opensearch] bootstrap complete"
