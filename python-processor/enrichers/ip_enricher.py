"""Classify an IP as internal / external / loopback / reserved.

Uses only Python stdlib so the enricher has no external dependencies and
stays fast. Results are memoized per-IP for the process lifetime.
"""
from __future__ import annotations

import ipaddress
from functools import lru_cache

from config import get_settings


def _internal_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    return [ipaddress.ip_network(c) for c in get_settings().internal_cidrs()]


@lru_cache(maxsize=10_000)
def classify_ip(ip: str) -> dict[str, str]:
    """Return classification + matching CIDR (empty if none)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return {"classification": "invalid", "cidr": ""}

    if addr.is_loopback:
        return {"classification": "loopback", "cidr": "127.0.0.0/8"}
    if addr.is_reserved or addr.is_multicast or addr.is_link_local:
        return {"classification": "reserved", "cidr": ""}

    for net in _internal_networks():
        if addr.version == net.version and addr in net:
            return {"classification": "internal", "cidr": str(net)}

    if addr.is_private:
        return {"classification": "internal", "cidr": "private"}

    return {"classification": "external", "cidr": ""}
