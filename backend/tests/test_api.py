"""End-to-end API tests using FastAPI's TestClient."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_datasets_listed():
    r = client.get("/api/datasets")
    assert r.status_code == 200
    names = {d["name"] for d in r.json()}
    assert {"customers", "orders", "products"}.issubset(names)


def test_run_and_summary_flow():
    run = client.post("/api/runs").json()
    assert run["total_checks"] >= 10
    assert run["failed"] >= 1  # injected issues must surface

    results = client.get("/api/results/latest").json()
    assert len(results) == run["total_checks"]

    summary = client.get("/api/summary").json()
    assert 0 <= summary["quality_score"] <= 100
    assert summary["open_incidents"] >= 1

    incidents = client.get("/api/incidents").json()
    assert any(i["status"] != "resolved" for i in incidents)


def test_profile_endpoint():
    r = client.get("/api/datasets/1/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["total_rows"] > 0
    assert any(col["null_count"] >= 0 for col in body["columns"])


def test_lineage_endpoint():
    r = client.get("/api/lineage")
    assert r.status_code == 200
    edges = r.json()
    assert any(e["upstream"] == "orders" for e in edges)
