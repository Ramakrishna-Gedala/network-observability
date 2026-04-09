"""Abstract async Kafka consumer.

Wraps `confluent_kafka.Consumer` with manual offset commits, a retry loop,
and a dead-letter fan-out to `zeek-alerts` on repeated processing failure.
Subclasses implement `process()` to enrich / detect / export a single event.
"""
from __future__ import annotations

import asyncio
import json
import signal
from abc import ABC, abstractmethod
from typing import Any

import structlog
from confluent_kafka import Consumer, KafkaError

from detectors.alert_publisher import AlertPublisher
from exporters.otel_exporter import OtelExporter

log = structlog.get_logger()

MAX_RETRIES = 3


class BaseConsumer(ABC):
    topic: str = ""
    group_id: str = ""

    def __init__(self, bootstrap_servers: str, alert_publisher: AlertPublisher) -> None:
        self._consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": self.group_id,
                "enable.auto.commit": False,
                "auto.offset.reset": "latest",
                "session.timeout.ms": 10_000,
            }
        )
        self._consumer.subscribe([self.topic])
        self._alert_publisher = alert_publisher
        self._running = False
        self._paused = False

    @abstractmethod
    async def process(self, event: dict[str, Any]) -> None:
        """Enrich, detect, export one event."""
        raise NotImplementedError

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        self._running = True
        loop = asyncio.get_running_loop()
        for sig_name in ("SIGTERM", "SIGINT"):
            try:
                loop.add_signal_handler(getattr(signal, sig_name), self.stop)
            except (NotImplementedError, RuntimeError):
                # Windows / already-set handler
                pass

        log.info("consumer_started", topic=self.topic, group=self.group_id)
        while self._running:
            if self._paused:
                await asyncio.sleep(0.5)
                continue

            msg = self._consumer.poll(0.5)
            if msg is None:
                await asyncio.sleep(0)
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                log.error("kafka_poll_error", topic=self.topic, error=str(msg.error()))
                continue

            try:
                event = json.loads(msg.value())
            except json.JSONDecodeError as exc:
                log.error("bad_json", topic=self.topic, error=str(exc))
                OtelExporter.record_processed(self.topic, "bad_json")
                self._consumer.commit(msg, asynchronous=False)
                continue

            await self._process_with_retry(event, msg)

        log.info("consumer_stopped", topic=self.topic)
        self._consumer.close()

    async def _process_with_retry(self, event: dict[str, Any], msg) -> None:  # type: ignore[no-untyped-def]
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await self.process(event)
                OtelExporter.record_processed(self.topic, "ok")
                self._consumer.commit(msg, asynchronous=False)
                return
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "processing_failed",
                    topic=self.topic,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt == MAX_RETRIES:
                    OtelExporter.record_processed(self.topic, "dead_letter")
                    self._alert_publisher.publish_alert(
                        {
                            "alert_type": "processing_error",
                            "topic": self.topic,
                            "error": str(exc),
                            "event": event,
                            "severity": "high",
                        }
                    )
                    self._consumer.commit(msg, asynchronous=False)
                    return
                await asyncio.sleep(0.5 * attempt)
