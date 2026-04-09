"""Publishes alerts to the zeek-alerts Kafka topic."""
from __future__ import annotations

import json
from typing import Any

import structlog
from confluent_kafka import Producer

log = structlog.get_logger()


class AlertPublisher:
    def __init__(self, bootstrap_servers: str, topic: str = "zeek-alerts") -> None:
        self.topic = topic
        self._producer = Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "enable.idempotence": True,
                "acks": "all",
                "compression.type": "gzip",
            }
        )

    def publish_alert(self, alert: dict[str, Any]) -> None:
        payload = json.dumps(alert, default=str).encode("utf-8")
        try:
            self._producer.produce(self.topic, payload)
            self._producer.poll(0)
        except BufferError:
            # local queue full — flush and retry once
            self._producer.flush(5.0)
            self._producer.produce(self.topic, payload)
        except Exception as exc:  # noqa: BLE001
            log.error("alert_publish_failed", error=str(exc), alert_type=alert.get("alert_type"))

    def flush(self, timeout: float = 5.0) -> None:
        self._producer.flush(timeout)
