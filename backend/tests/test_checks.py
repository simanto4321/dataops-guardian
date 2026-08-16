"""Unit tests for the data-quality rule engine against seeded fixtures."""
from __future__ import annotations

from app import checks as engine


def test_not_null_detects_injected_nulls():
    outcome, duration = engine.execute_check("not_null", "customers", "email", {"max_failure_rate": 0.0})
    assert outcome.status == "fail"
    assert outcome.rows_failed > 0
    assert duration >= 0.0


def test_unique_detects_duplicate_emails():
    outcome, _ = engine.execute_check("unique", "customers", "email", {})
    assert outcome.status == "fail"
    assert outcome.rows_failed >= 3  # three duplicates injected


def test_unique_passes_on_primary_key():
    outcome, _ = engine.execute_check("unique", "customers", "id", {})
    assert outcome.status == "pass"


def test_range_flags_negative_price():
    outcome, _ = engine.execute_check("range", "products", "price", {"min": 0})
    assert outcome.status == "fail"
    assert outcome.rows_failed == 2


def test_accepted_values_flags_bad_status():
    outcome, _ = engine.execute_check(
        "accepted_values", "orders", "status",
        {"values": ["pending", "paid", "shipped", "delivered", "cancelled"]},
    )
    assert outcome.status == "fail"
    assert outcome.rows_failed == 3


def test_range_flags_negative_quantity():
    outcome, _ = engine.execute_check("range", "order_items", "quantity", {"min": 1})
    assert outcome.status == "fail"
    assert outcome.rows_failed == 3


def test_freshness_fails_on_stale_table():
    outcome, _ = engine.execute_check("freshness", "daily_revenue", "created_at", {"sla_minutes": 1440})
    assert outcome.status == "fail"


def test_freshness_passes_on_fresh_orders():
    outcome, _ = engine.execute_check("freshness", "orders", "created_at", {"sla_minutes": 4320})
    assert outcome.status == "pass"


def test_schema_check_passes_for_known_columns():
    outcome, _ = engine.execute_check(
        "schema", "orders", None, {"columns": ["id", "customer_id", "status", "total", "created_at"]}
    )
    assert outcome.status == "pass"


def test_schema_check_detects_drift():
    outcome, _ = engine.execute_check("schema", "orders", None, {"columns": ["id", "nonexistent_col"]})
    assert outcome.status == "fail"
    assert "nonexistent_col" in outcome.message


def test_missing_table_is_error_not_exception():
    outcome, _ = engine.execute_check("not_null", "no_such_table", "x", {})
    assert outcome.status == "error"


def test_unsafe_identifier_rejected():
    outcome, _ = engine.execute_check("not_null", "orders", "status; DROP TABLE orders", {})
    assert outcome.status == "error"
