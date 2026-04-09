"""Model for a Zeek conn.log event."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ConnEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: float | str | None = None
    uid: str | None = None
    src_ip: str | None = Field(None, alias="id.orig_h")
    src_port: int | None = Field(None, alias="id.orig_p")
    dst_ip: str | None = Field(None, alias="id.resp_h")
    dst_port: int | None = Field(None, alias="id.resp_p")
    proto: str | None = None
    service: str | None = None
    duration: float | None = None
    bytes_sent: int | None = Field(None, alias="orig_bytes")
    bytes_recv: int | None = Field(None, alias="resp_bytes")
    conn_state: str | None = None

    # enrichment / alert decorations (populated post-parse)
    ip_classification: str | None = None
    alert_type: str | None = None
