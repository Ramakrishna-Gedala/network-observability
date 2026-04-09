"""NetWatch processor — FastAPI app + Kafka consumer tasks."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from api.routers import alerts as alerts_router
from api.routers import config as config_router
from api.routers import consumers as consumers_router
from api.routers import health as health_router
from api.routers import search as search_router
from api.routers import stats as stats_router
from config import get_settings
from consumers.conn_consumer import ConnConsumer
from consumers.dns_consumer import DnsConsumer
from consumers.http_consumer import HttpConsumer
from detectors.alert_publisher import AlertPublisher
from exporters.opensearch_exporter import OpenSearchExporter

logging.basicConfig(level=logging.INFO, format="%(message)s")
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    exporter = OpenSearchExporter(settings.opensearch_url, settings.opensearch_index_prefix)
    alert_publisher = AlertPublisher(settings.kafka_bootstrap_servers)

    consumers = {
        "zeek-conn": ConnConsumer(
            settings.kafka_bootstrap_servers,
            alert_publisher,
            exporter,
            settings.alert_threshold_requests_per_minute,
        ),
        "zeek-dns": DnsConsumer(
            settings.kafka_bootstrap_servers, alert_publisher, exporter
        ),
        "zeek-http": HttpConsumer(
            settings.kafka_bootstrap_servers,
            alert_publisher,
            exporter,
            settings.alert_threshold_requests_per_minute,
        ),
    }

    app.state.exporter = exporter
    app.state.alert_publisher = alert_publisher
    app.state.consumers = consumers

    tasks: list[asyncio.Task[Any]] = [
        asyncio.create_task(c.run(), name=f"consumer:{topic}")
        for topic, c in consumers.items()
    ]

    # periodic flusher — bulk-index buffered events even if batch isn't full
    async def periodic_flush() -> None:
        while True:
            try:
                await exporter.flush()
            except Exception as exc:  # noqa: BLE001
                log.warning("flush_failed", error=str(exc))
            await asyncio.sleep(5)

    tasks.append(asyncio.create_task(periodic_flush(), name="exporter-flush"))

    log.info("processor_started", topics=list(consumers.keys()))
    try:
        yield
    finally:
        log.info("processor_stopping")
        for c in consumers.values():
            c.stop()
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        alert_publisher.flush()
        await exporter.close()


app = FastAPI(title="NetWatch Processor", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_allow_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(health_router.router)
app.include_router(stats_router.router)
app.include_router(alerts_router.router)
app.include_router(search_router.router)
app.include_router(config_router.router)
app.include_router(consumers_router.router)

Instrumentator().instrument(app).expose(app, include_in_schema=False, endpoint="/metrics")
