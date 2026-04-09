"""Consumer for the zeek-dns topic."""
from __future__ import annotations

from typing import Any

from detectors.alert_publisher import AlertPublisher
from detectors.dns_tunneling import DnsTunnelingDetector
from enrichers.ip_enricher import classify_ip
from exporters.opensearch_exporter import OpenSearchExporter
from exporters.otel_exporter import OtelExporter
from models.dns_event import DnsEvent

from .base_consumer import BaseConsumer


class DnsConsumer(BaseConsumer):
    topic = "zeek-dns"
    group_id = "netwatch-processor-dns"

    def __init__(
        self,
        bootstrap_servers: str,
        alert_publisher: AlertPublisher,
        exporter: OpenSearchExporter,
    ) -> None:
        super().__init__(bootstrap_servers, alert_publisher)
        self._exporter = exporter
        self._tunneling = DnsTunnelingDetector()

    async def process(self, event: dict[str, Any]) -> None:
        parsed = DnsEvent.model_validate(event)
        doc = parsed.model_dump(exclude_none=True, by_alias=False)

        if parsed.src_ip:
            doc["ip_classification"] = classify_ip(parsed.src_ip)["classification"]

        for alert in self._tunneling.inspect(doc):
            self._alert_publisher.publish_alert(alert)
            OtelExporter.record_alert(alert["alert_type"], alert.get("severity", "medium"))
            doc["alert_type"] = alert["alert_type"]
            await self._exporter.add("alerts", alert)

        await self._exporter.add("dns", doc)
