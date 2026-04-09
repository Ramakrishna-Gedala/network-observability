"""Consumer for the zeek-conn topic."""
from __future__ import annotations

from typing import Any

from detectors.alert_publisher import AlertPublisher
from detectors.high_volume import HighVolumeDetector
from detectors.port_scan import PortScanDetector
from enrichers.ip_enricher import classify_ip
from exporters.opensearch_exporter import OpenSearchExporter
from exporters.otel_exporter import OtelExporter
from models.conn_event import ConnEvent

from .base_consumer import BaseConsumer


class ConnConsumer(BaseConsumer):
    topic = "zeek-conn"
    group_id = "netwatch-processor-conn"

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
        self._port_scan = PortScanDetector()

    async def process(self, event: dict[str, Any]) -> None:
        parsed = ConnEvent.model_validate(event)
        doc = parsed.model_dump(exclude_none=True, by_alias=False)

        if parsed.src_ip:
            doc["ip_classification"] = classify_ip(parsed.src_ip)["classification"]

        alerts = self._high_volume.inspect(doc) + self._port_scan.inspect(doc)
        for alert in alerts:
            self._alert_publisher.publish_alert(alert)
            OtelExporter.record_alert(alert["alert_type"], alert.get("severity", "medium"))
            doc["alert_type"] = alert["alert_type"]
            await self._exporter.add("alerts", alert)

        await self._exporter.add("conn", doc)
