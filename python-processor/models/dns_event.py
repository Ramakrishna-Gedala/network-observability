"""Model for a Zeek dns.log event."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DnsEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: float | str | None = None
    uid: str | None = None
    src_ip: str | None = Field(None, alias="id.orig_h")
    query: str | None = None
    qtype_name: str | None = None
    answers: list[str] | None = None
    rtt: float | None = None

    ip_classification: str | None = None
    alert_type: str | None = None
