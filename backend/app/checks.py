"""The data-quality rule engine.

Each check compiles to portable SQL, runs against the observed warehouse and
returns a normalized :class:`CheckOutcome`. Supported check types:

- ``not_null``        : fails if a column contains NULLs (optional threshold).
- ``unique``          : fails if a column has duplicate values.
- ``accepted_values`` : fails if values fall outside an allowed set.
- ``range``           : fails if a numeric column falls outside [min, max].
- ``freshness``       : fails if the newest timestamp is older than the SLA.
- ``row_count``       : fails if row count is outside [min, max].
- ``schema``          : fails if expected columns are missing (schema drift).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from dateutil import parser as date_parser

from . import warehouse


@dataclass
class CheckOutcome:
    status: str  # pass | fail | error
    observed_value: float | None
    rows_scanned: int
    rows_failed: int
    message: str


def _quote(identifier: str) -> str:
    if not identifier or not identifier.replace("_", "").isalnum():
        raise ValueError(f"unsafe identifier: {identifier!r}")
    return f'"{identifier}"'


def _row_count(table: str) -> int:
    return int(warehouse.scalar(f"SELECT COUNT(*) FROM {_quote(table)}") or 0)


def _threshold(config: dict, default: float = 0.0) -> float:
    """Allowed failure rate (0..1). 0 means zero tolerance."""
    return float(config.get("max_failure_rate", default))


def check_not_null(table: str, column: str, config: dict) -> CheckOutcome:
    total = _row_count(table)
    failed = int(warehouse.scalar(f"SELECT COUNT(*) FROM {_quote(table)} WHERE {_quote(column)} IS NULL") or 0)
    rate = failed / total if total else 0.0
    ok = rate <= _threshold(config)
    return CheckOutcome(
        status="pass" if ok else "fail",
        observed_value=round(rate, 4),
        rows_scanned=total,
        rows_failed=failed,
        message=f"{failed}/{total} NULL ({rate:.2%}) in {column}",
    )


def check_unique(table: str, column: str, config: dict) -> CheckOutcome:
    total = _row_count(table)
    dupes = warehouse.fetch_all(
        f"SELECT {_quote(column)} AS v, COUNT(*) AS n FROM {_quote(table)} "
        f"GROUP BY {_quote(column)} HAVING COUNT(*) > 1"
    )
    rows_failed = sum(int(d["n"]) for d in dupes)
    ok = rows_failed <= int(config.get("max_duplicates", 0))
    sample = ", ".join(str(d["v"]) for d in dupes[:3])
    return CheckOutcome(
        status="pass" if ok else "fail",
        observed_value=float(len(dupes)),
        rows_scanned=total,
        rows_failed=rows_failed,
        message=f"{len(dupes)} duplicate value(s) in {column}" + (f" e.g. {sample}" if sample else ""),
    )


def check_accepted_values(table: str, column: str, config: dict) -> CheckOutcome:
    allowed = config.get("values", [])
    if not allowed:
        raise ValueError("accepted_values check requires config.values")
    total = _row_count(table)
    placeholders = ", ".join(f":v{i}" for i in range(len(allowed)))
    params = {f"v{i}": val for i, val in enumerate(allowed)}
    failed = int(
        warehouse.scalar(
            f"SELECT COUNT(*) FROM {_quote(table)} "
            f"WHERE {_quote(column)} IS NOT NULL AND {_quote(column)} NOT IN ({placeholders})",
            params,
        )
        or 0
    )
    ok = failed <= 0
    return CheckOutcome(
        status="pass" if ok else "fail",
        observed_value=float(failed),
        rows_scanned=total,
        rows_failed=failed,
        message=f"{failed} row(s) outside allowed set {allowed} in {column}",
    )


def check_range(table: str, column: str, config: dict) -> CheckOutcome:
    lo = config.get("min")
    hi = config.get("max")
    if lo is None and hi is None:
        raise ValueError("range check requires config.min and/or config.max")
    total = _row_count(table)
    clauses, params = [], {}
    if lo is not None:
        clauses.append(f"{_quote(column)} < :lo")
        params["lo"] = lo
    if hi is not None:
        clauses.append(f"{_quote(column)} > :hi")
        params["hi"] = hi
    where = " OR ".join(clauses)
    failed = int(
        warehouse.scalar(
            f"SELECT COUNT(*) FROM {_quote(table)} WHERE {_quote(column)} IS NOT NULL AND ({where})", params
        )
        or 0
    )
    ok = failed <= 0
    return CheckOutcome(
        status="pass" if ok else "fail",
        observed_value=float(failed),
        rows_scanned=total,
        rows_failed=failed,
        message=f"{failed} row(s) outside [{lo}, {hi}] in {column}",
    )


def check_freshness(table: str, column: str, config: dict) -> CheckOutcome:
    sla_minutes = float(config.get("sla_minutes", 1440))
    newest = warehouse.scalar(f"SELECT MAX({_quote(column)}) FROM {_quote(table)}")
    if newest is None:
        return CheckOutcome("fail", None, _row_count(table), 0, f"no timestamps in {column}")
    if isinstance(newest, str):
        newest_dt = date_parser.parse(newest)
    elif isinstance(newest, datetime):
        newest_dt = newest
    else:
        return CheckOutcome("error", None, 0, 0, f"unsupported timestamp type for {column}")
    if newest_dt.tzinfo is None:
        newest_dt = newest_dt.replace(tzinfo=timezone.utc)
    age_minutes = (datetime.now(timezone.utc) - newest_dt).total_seconds() / 60.0
    ok = age_minutes <= sla_minutes
    return CheckOutcome(
        status="pass" if ok else "fail",
        observed_value=round(age_minutes, 1),
        rows_scanned=_row_count(table),
        rows_failed=0 if ok else 1,
        message=f"newest row is {age_minutes:.0f} min old (SLA {sla_minutes:.0f} min)",
    )


def check_row_count(table: str, config: dict) -> CheckOutcome:
    total = _row_count(table)
    lo = config.get("min")
    hi = config.get("max")
    ok = True
    if lo is not None and total < lo:
        ok = False
    if hi is not None and total > hi:
        ok = False
    return CheckOutcome(
        status="pass" if ok else "fail",
        observed_value=float(total),
        rows_scanned=total,
        rows_failed=0 if ok else total,
        message=f"row_count={total} expected [{lo}, {hi}]",
    )


def check_schema(table: str, config: dict) -> CheckOutcome:
    expected = set(config.get("columns", []))
    if not expected:
        raise ValueError("schema check requires config.columns")
    actual = {c["name"] for c in warehouse.list_columns(table)}
    missing = sorted(expected - actual)
    ok = not missing
    return CheckOutcome(
        status="pass" if ok else "fail",
        observed_value=float(len(missing)),
        rows_scanned=0,
        rows_failed=len(missing),
        message="schema matches" if ok else f"missing columns: {missing}",
    )


def execute_check(check_type: str, table: str, column: str | None, config: dict) -> tuple[CheckOutcome, float]:
    """Run a single check and time it.

    Never raises: any failure becomes a structured ``error`` outcome. Returns the
    outcome plus wall-clock duration in milliseconds.
    """
    start = time.perf_counter()
    try:
        if not warehouse.table_exists(table):
            outcome = CheckOutcome("error", None, 0, 0, f"table {table!r} not found")
        elif check_type == "not_null":
            outcome = check_not_null(table, column, config)
        elif check_type == "unique":
            outcome = check_unique(table, column, config)
        elif check_type == "accepted_values":
            outcome = check_accepted_values(table, column, config)
        elif check_type == "range":
            outcome = check_range(table, column, config)
        elif check_type == "freshness":
            outcome = check_freshness(table, column, config)
        elif check_type == "row_count":
            outcome = check_row_count(table, config)
        elif check_type == "schema":
            outcome = check_schema(table, config)
        else:
            outcome = CheckOutcome("error", None, 0, 0, f"unknown check type {check_type!r}")
    except Exception as exc:  # noqa: BLE001 - surface as a structured error result
        outcome = CheckOutcome("error", None, 0, 0, f"{type(exc).__name__}: {exc}")
    duration_ms = round((time.perf_counter() - start) * 1000.0, 2)
    return outcome, duration_ms
