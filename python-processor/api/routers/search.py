"""Log explorer search API — thin pass-through to OpenSearch."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from opensearchpy import AsyncOpenSearch

from config import get_settings

router = APIRouter(prefix="/api", tags=["search"])

IndexType = Literal["conn", "dns", "http", "alerts"]


@router.get("/search")
async def search(
    q: str = Query("*", description="Lucene query string"),
    index: IndexType = Query("conn"),
    size: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    settings = get_settings()
    if index == "alerts":
        target = f"{settings.opensearch_index_prefix}-alerts"
    else:
        target = f"{settings.opensearch_index_prefix}-{index}-*"

    client = AsyncOpenSearch(hosts=[settings.opensearch_url], verify_certs=False)
    try:
        resp = await client.search(
            index=target,
            body={
                "size": size,
                "from": offset,
                "sort": [{"@timestamp": {"order": "desc", "unmapped_type": "date"}}],
                "query": {"query_string": {"query": q}},
            },
            ignore=[404],
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()

    raw_hits = (resp or {}).get("hits", {}).get("hits", [])
    total = (resp or {}).get("hits", {}).get("total", {})
    total_value = total.get("value", 0) if isinstance(total, dict) else 0

    return {
        "hits": [h.get("_source", {}) for h in raw_hits],
        "total": total_value,
        "index": target,
    }
