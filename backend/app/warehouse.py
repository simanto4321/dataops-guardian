"""Thin accessor over the *observed* warehouse.

The warehouse is a separate logical database (its own SQLAlchemy engine) that we
introspect and query read-only. Keeping this isolated from the control-plane
store mirrors how a real data-quality tool points at Snowflake/BigQuery/Postgres
while storing its own metadata elsewhere.
"""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from .config import get_settings


@lru_cache
def warehouse_engine() -> Engine:
    url = get_settings().effective_warehouse_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    # Read-mostly connection; pool_pre_ping keeps long-lived Postgres pools healthy.
    return create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)


def list_tables() -> list[str]:
    return sorted(inspect(warehouse_engine()).get_table_names())


def list_columns(table: str) -> list[dict]:
    insp = inspect(warehouse_engine())
    cols = []
    for col in insp.get_columns(table):
        cols.append({"name": col["name"], "type": str(col["type"]), "nullable": bool(col.get("nullable", True))})
    return cols


def table_exists(table: str) -> bool:
    return table in set(inspect(warehouse_engine()).get_table_names())


def scalar(sql: str, params: dict | None = None):
    with warehouse_engine().connect() as conn:
        return conn.execute(text(sql), params or {}).scalar()


def fetch_all(sql: str, params: dict | None = None) -> list[dict]:
    with warehouse_engine().connect() as conn:
        rows = conn.execute(text(sql), params or {}).mappings().all()
        return [dict(r) for r in rows]
