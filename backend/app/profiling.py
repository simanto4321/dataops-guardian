"""Column profiling for observed warehouse tables.

Produces null rate, distinct count, approximate uniqueness and simple numeric
stats using portable SQL that works on both SQLite and PostgreSQL.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from . import warehouse


def _quote(identifier: str) -> str:
    # Defensive identifier quoting. Warehouse table/column names come from schema
    # introspection (not user input), but we still whitelist characters and quote.
    if not identifier.replace("_", "").isalnum():
        raise ValueError(f"unsafe identifier: {identifier!r}")
    return f'"{identifier}"'


@dataclass
class ColumnProfile:
    column: str
    data_type: str
    total_rows: int
    null_count: int
    null_rate: float
    distinct_count: int
    unique_rate: float
    min_value: str | None
    max_value: str | None

    def as_dict(self) -> dict:
        return asdict(self)


def profile_column(table: str, column: str, data_type: str, total_rows: int) -> ColumnProfile:
    t, c = _quote(table), _quote(column)
    null_count = warehouse.scalar(f"SELECT COUNT(*) FROM {t} WHERE {c} IS NULL") or 0
    distinct_count = warehouse.scalar(f"SELECT COUNT(DISTINCT {c}) FROM {t}") or 0
    min_value = warehouse.scalar(f"SELECT MIN({c}) FROM {t}")
    max_value = warehouse.scalar(f"SELECT MAX({c}) FROM {t}")
    non_null = max(total_rows - null_count, 0)
    return ColumnProfile(
        column=column,
        data_type=data_type,
        total_rows=total_rows,
        null_count=int(null_count),
        null_rate=round(null_count / total_rows, 4) if total_rows else 0.0,
        distinct_count=int(distinct_count),
        unique_rate=round(distinct_count / non_null, 4) if non_null else 0.0,
        min_value=None if min_value is None else str(min_value),
        max_value=None if max_value is None else str(max_value),
    )


def profile_table(table: str) -> dict:
    total_rows = warehouse.scalar(f"SELECT COUNT(*) FROM {_quote(table)}") or 0
    columns = warehouse.list_columns(table)
    profiles = [profile_column(table, col["name"], col["type"], total_rows).as_dict() for col in columns]
    return {"table": table, "total_rows": int(total_rows), "columns": profiles}
