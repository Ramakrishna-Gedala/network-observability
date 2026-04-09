"""Consumer pause/resume control API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_consumer_registry

router = APIRouter(prefix="/api/consumers", tags=["consumers"])


def _lookup(consumers: dict, topic: str):  # type: ignore[no-untyped-def]
    consumer = consumers.get(topic)
    if consumer is None:
        raise HTTPException(status_code=404, detail=f"unknown topic: {topic}")
    return consumer


@router.post("/{topic}/pause")
async def pause(topic: str, consumers: dict = Depends(get_consumer_registry)) -> dict[str, str]:
    consumer = _lookup(consumers, topic)
    consumer.pause()
    return {"topic": topic, "status": "paused"}


@router.post("/{topic}/resume")
async def resume(topic: str, consumers: dict = Depends(get_consumer_registry)) -> dict[str, str]:
    consumer = _lookup(consumers, topic)
    consumer.resume()
    return {"topic": topic, "status": "running"}
