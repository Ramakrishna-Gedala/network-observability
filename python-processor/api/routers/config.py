"""Runtime configuration API.

Exposes a subset of processor knobs for live tuning by the operator UI.
Changes are held in-process only (not persisted) — restart reverts them
to whatever the environment provides.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.dependencies import get_consumer_registry
from config import get_settings

router = APIRouter(prefix="/api", tags=["config"])


class ConfigPatch(BaseModel):
    alert_threshold_requests_per_minute: int | None = Field(None, ge=1)


@router.get("/config")
async def read_config(consumers: dict = Depends(get_consumer_registry)) -> dict[str, Any]:
    settings = get_settings()
    # Pull live threshold from the conn consumer's detector (it's the
    # authoritative source once the app is running).
    conn = consumers.get("zeek-conn")
    live_threshold = (
        conn._high_volume.threshold if conn is not None else settings.alert_threshold_requests_per_minute  # type: ignore[attr-defined]
    )
    return {
        "alert_threshold_requests_per_minute": live_threshold,
        "internal_cidr_ranges": settings.internal_cidrs(),
        "opensearch_index_prefix": settings.opensearch_index_prefix,
    }


@router.patch("/config")
async def update_config(
    patch: ConfigPatch,
    consumers: dict = Depends(get_consumer_registry),
) -> dict[str, Any]:
    if patch.alert_threshold_requests_per_minute is not None:
        new_threshold = patch.alert_threshold_requests_per_minute
        for topic in ("zeek-conn", "zeek-http"):
            consumer = consumers.get(topic)
            if consumer is not None and hasattr(consumer, "_high_volume"):
                consumer._high_volume.threshold = new_threshold  # type: ignore[attr-defined]
    return await read_config(consumers)
