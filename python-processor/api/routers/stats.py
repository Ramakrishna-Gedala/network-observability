"""Pipeline throughput stats API."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_consumer_registry
from exporters.otel_exporter import events_processed_total

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
async def stats(consumers: dict = Depends(get_consumer_registry)) -> dict:
    # pull raw counter samples for each topic/status
    by_topic: dict[str, dict[str, float]] = {}
    for metric in events_processed_total.collect():
        for sample in metric.samples:
            if sample.name != "events_processed_total":
                continue
            topic = sample.labels.get("topic", "unknown")
            status = sample.labels.get("status", "ok")
            by_topic.setdefault(topic, {})[status] = sample.value

    return {
        "topics": by_topic,
        "consumers": {
            topic: {"paused": consumer._paused, "running": consumer._running}
            for topic, consumer in consumers.items()
        },
    }
