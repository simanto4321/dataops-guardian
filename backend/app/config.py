"""Application configuration.

Defaults to a zero-setup SQLite database so the project runs with no external
services. Point ``DATAOPS_DATABASE_URL`` at PostgreSQL for the production path
(see ``docker-compose.yml``), e.g.::

    postgresql+psycopg2://dataops:dataops@localhost:5432/dataops
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATAOPS_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./dataops.db"
    # Warehouse under observation. Defaults to the same DB for a single-file demo,
    # but can point at a separate analytics warehouse in real deployments.
    warehouse_url: str | None = None
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    api_title: str = "DataOps Guardian API"

    @property
    def effective_warehouse_url(self) -> str:
        return self.warehouse_url or self.database_url

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
