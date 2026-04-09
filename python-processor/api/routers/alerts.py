"""Recent-alerts API.

Reads from OpenSearch's `netwatch-alerts` index. Also exposes a webhook
endpoint that accepts an alert JSON and optionally forwards to Slack.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Body, Depends, HTTPException
from opensearchpy import AsyncOpenSearch

from api.dependencies import get_alert_publisher
from config import get_settings
from detectors.alert_publisher import AlertPublisher

log = structlog.get_logger()
router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts")
async def list_alerts(limit: int = 50) -> dict[str, Any]:
    settings = get_settings()
    client = AsyncOpenSearch(hosts=[settings.opensearch_url], verify_certs=False)
    try:
        resp = await client.search(
            index=f"{settings.opensearch_index_prefix}-alerts",
            body={
                "size": min(limit, 500),
                "sort": [{"ts": {"order": "desc"}}],
                "query": {"match_all": {}},
            },
            ignore=[404],
        )
    finally:
        await client.close()

    hits = (resp or {}).get("hits", {}).get("hits", [])
    return {"alerts": [h.get("_source", {}) for h in hits]}


@router.post("/webhooks/alert")
async def alert_webhook(
    alert: dict[str, Any] = Body(...),
    publisher: AlertPublisher = Depends(get_alert_publisher),
) -> dict[str, str]:
    if not isinstance(alert, dict) or "alert_type" not in alert:
        raise HTTPException(status_code=400, detail="alert must include alert_type")

    publisher.publish_alert(alert)

    slack_url = os.environ.get("SLACK_WEBHOOK_URL") or get_settings().slack_webhook_url
    if slack_url:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    slack_url,
                    json={
                        "text": f":rotating_light: NetWatch alert: "
                        f"{alert.get('alert_type')} / severity={alert.get('severity', 'n/a')} / "
                        f"src_ip={alert.get('src_ip', 'n/a')}"
                    },
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("slack_forward_failed", error=str(exc))

    return {"status": "accepted"}
