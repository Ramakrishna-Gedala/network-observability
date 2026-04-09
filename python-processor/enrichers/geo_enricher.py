"""Stub for GeoIP enrichment.

A real implementation would use a MaxMind GeoLite2 database or an external
API. We keep the signature here so callers can wire in a backend without
touching the consumer/exporter pipeline.
"""
from __future__ import annotations


def geo_lookup(ip: str) -> dict[str, str | None]:
    """Return a geo record for the given IP.

    Currently returns a placeholder. Replace with a MaxMind reader when a
    DB is mounted into the container.
    """
    return {
        "country": None,
        "country_code": None,
        "city": None,
        "asn": None,
    }
