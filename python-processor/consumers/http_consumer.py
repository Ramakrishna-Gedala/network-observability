"""Consumer for the zeek-http topic."""
from __future__ import annotations

from typing import Any

from detectors.alert_publisher import AlertPublisher
from detectors.high_volume import HighVolumeDetector
from enrichers.ip_enricher import classify_ip
from exporters.opensearch_exporter import OpenSearchExporter
from exporters.otel_exporter import OtelExporter
from models.http_event import HttpEvent

from .base_consumer import BaseConsumer


class HttpConsumer(BaseConsumer):
    topic = "zeek-http"
    group_id = "netwatch-processor-http"

    def __init__(
        self,
        bootstrap_servers: str,
        alert_publisher: AlertPublisher,
        exporter: OpenSearchExporter,
        high_volume_threshold: int,
    ) -> None:
        super().__init__(bootstrap_servers, alert_publisher)
        self._exporter = exporter
        self._high_volume = HighVolumeDetector(threshold_per_minute=high_volume_threshold)

    async def process(self, event: dict[str, Any]) -> None:
        parsed = HttpEvent.model_validate(event)
        doc = parsed.model_dump(exclude_none=True, by_alias=False)

        if parsed.src_ip:
            doc["ip_classification"] = classify_ip(parsed.src_ip)["classification"]

        for alert in self._high_volume.inspect(doc):
            self._alert_publisher.publish_alert(alert)
            OtelExporter.record_alert(alert["alert_type"], alert.get("severity", "medium"))
            doc["alert_type"] = alert["alert_type"]
            await self._exporter.add("alerts", alert)

        await self._exporter.add("http", doc)
