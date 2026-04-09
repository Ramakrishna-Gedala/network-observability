"""Bulk index enriched events into date-stamped OpenSearch indices."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch
from opensearchpy.helpers import async_bulk

log = structlog.get_logger()


class OpenSearchExporter:
    def __init__(self, url: str, index_prefix: str = "netwatch") -> None:
        self._client = AsyncOpenSearch(hosts=[url], verify_certs=False)
        self._prefix = index_prefix
        self._buffer: dict[str, list[dict[str, Any]]] = {}
        self._batch_size = 100

    def _index_name(self, log_type: str) -> str:
        if log_type == "alerts":
            return f"{self._prefix}-alerts"
        day = datetime.now(timezone.utc).strftime("%Y.%m.%d")
        return f"{self._prefix}-{log_type}-{day}"

    async def add(self, log_type: str, document: dict[str, Any]) -> None:
        buf = self._buffer.setdefault(log_type, [])
        buf.append(document)
        if len(buf) >= self._batch_size:
            await self.flush(log_type)

    async def flush(self, log_type: str | None = None) -> None:
        log_types = [log_type] if log_type else list(self._buffer.keys())
        for lt in log_types:
            docs = self._buffer.get(lt) or []
            if not docs:
                continue
            index = self._index_name(lt)
            actions = [{"_index": index, "_source": d} for d in docs]
            try:
                await async_bulk(self._client, actions, raise_on_error=False)
            except Exception as exc:  # noqa: BLE001
                log.error("opensearch_bulk_failed", log_type=lt, error=str(exc))
            finally:
                self._buffer[lt] = []

    async def close(self) -> None:
        await self.flush()
        await self._client.close()
