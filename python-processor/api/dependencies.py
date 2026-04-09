"""Shared FastAPI dependency providers.

The pipeline singletons (exporter, alert publisher, consumer registry)
are attached to `app.state` at startup and pulled back out here.
"""
from __future__ import annotations

from fastapi import Request

from detectors.alert_publisher import AlertPublisher
from exporters.opensearch_exporter import OpenSearchExporter


def get_exporter(request: Request) -> OpenSearchExporter:
    return request.app.state.exporter  # type: ignore[no-any-return]


def get_alert_publisher(request: Request) -> AlertPublisher:
    return request.app.state.alert_publisher  # type: ignore[no-any-return]


def get_consumer_registry(request: Request) -> dict:
    return request.app.state.consumers  # type: ignore[no-any-return]
