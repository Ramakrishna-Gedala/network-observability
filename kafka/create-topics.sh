#!/usr/bin/env bash
#
# Create the NetWatch Kafka topics. Intended to be exec'd inside the
# Confluent Kafka container, or invoked via the `make topics` target.
#
# Usage (inside container):
#   /bin/bash /kafka/create-topics.sh
#
set -euo pipefail

BOOTSTRAP="${KAFKA_BOOTSTRAP:-kafka:9092}"

create_topic () {
    local name="$1" partitions="$2" replication="$3" retention_ms="$4"
    echo "[kafka] creating topic ${name} (partitions=${partitions}, retention=${retention_ms}ms)"
    kafka-topics --bootstrap-server "${BOOTSTRAP}" \
        --create --if-not-exists \
        --topic "${name}" \
        --partitions "${partitions}" \
        --replication-factor "${replication}" \
        --config "retention.ms=${retention_ms}"
}

# 24h retention = 86_400_000 ms
create_topic zeek-conn   3 1 86400000
create_topic zeek-dns    3 1 86400000
create_topic zeek-http   3 1 86400000

# 7d retention = 604_800_000 ms
create_topic zeek-alerts 1 1 604800000

echo "[kafka] topics ready:"
kafka-topics --bootstrap-server "${BOOTSTRAP}" --list
