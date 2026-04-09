"""Model for a Zeek http.log event."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HttpEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: float | str | None = None
    uid: str | None = None
    src_ip: str | None = Field(None, alias="id.orig_h")
    dst_ip: str | None = Field(None, alias="id.resp_h")
    method: str | None = None
    host: str | None = None
    uri: str | None = None
    status_code: int | None = None
    response_body_len: int | None = None
    user_agent: str | None = Field(None, alias="user_agent")

    ip_classification: str | None = None
    alert_type: str | None = None
