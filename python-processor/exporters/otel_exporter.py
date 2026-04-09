"""Thin wrapper around the Prometheus client for processor metrics.

Traces/logs to OTEL collector happen via standard OTLP SDK; metrics are
exposed via `/metrics` on the FastAPI app and scraped by the collector.
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram

events_processed_total = Counter(
    "events_processed_total",
    "Count of events processed by the Kafka consumer pipeline",
    labelnames=("topic", "status"),
)

alerts_emitted_total = Counter(
    "alerts_emitted_total",
    "Count of anomaly alerts emitted by detectors",
    labelnames=("alert_type", "severity"),
)

event_processing_latency_seconds = Histogram(
    "event_processing_latency_seconds",
    "Per-event processing latency",
    labelnames=("topic",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)


class OtelExporter:
    """Placeholder — metrics are registered at module load.

    Having a class makes dependency injection tidy if we later add OTLP
    span exporters alongside Prometheus metrics.
    """

    @staticmethod
    def record_processed(topic: str, status: str) -> None:
        events_processed_total.labels(topic=topic, status=status).inc()

    @staticmethod
    def record_alert(alert_type: str, severity: str) -> None:
        alerts_emitted_total.labels(alert_type=alert_type, severity=severity).inc()
