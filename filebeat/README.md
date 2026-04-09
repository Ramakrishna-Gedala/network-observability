# filebeat/

**What lives here:** The `filebeat.yml` configuration that tails Zeek's JSON logs and ships them to Kafka.

**Why it exists:** Filebeat provides a reliable, at-least-once shipping layer between disk-based Zeek logs and Kafka. It handles file rotation, offset tracking, backoff, and compression so the Python processor can stay a pure consumer.

**How it connects to the next stage:** Filebeat reads from [../zeek/logs/](../zeek/logs/) and writes to Kafka topics `zeek-conn`, `zeek-dns`, `zeek-http` based on the `log_type` field. From there the [../python-processor/](../python-processor/) consumes each topic in its own consumer group.
