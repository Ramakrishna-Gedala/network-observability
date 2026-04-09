"""Environment-backed configuration for the NetWatch processor."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kafka_bootstrap_servers: str = Field("kafka:9092", alias="KAFKA_BOOTSTRAP_SERVERS")
    opensearch_url: str = Field("http://opensearch:9200", alias="OPENSEARCH_URL")
    opensearch_index_prefix: str = Field("netwatch", alias="OPENSEARCH_INDEX_PREFIX")

    internal_cidr_ranges: str = Field(
        "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
        alias="INTERNAL_CIDR_RANGES",
    )

    alert_threshold_requests_per_minute: int = Field(
        1000, alias="ALERT_THRESHOLD_REQUESTS_PER_MINUTE"
    )

    postgres_dsn: str = Field(
        "postgresql+asyncpg://netwatch:netwatch_dev@postgres:5432/netwatch",
        alias="POSTGRES_DSN",
    )

    slack_webhook_url: str | None = Field(None, alias="SLACK_WEBHOOK_URL")

    cors_allow_origins: str = Field("http://localhost:3000", alias="CORS_ALLOW_ORIGINS")

    def internal_cidrs(self) -> list[str]:
        return [c.strip() for c in self.internal_cidr_ranges.split(",") if c.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
