"""Pytest fixtures: spin up an isolated SQLite warehouse + control plane per session."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Point the app at a throwaway database *before* app modules import their engines.
_TMP_DIR = tempfile.mkdtemp(prefix="dataops_test_")
_DB_PATH = Path(_TMP_DIR) / "test.db"
os.environ["DATAOPS_DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"


@pytest.fixture(scope="session", autouse=True)
def seeded_db():
    from app.seed import seed_all

    seed_all()
    yield


@pytest.fixture
def session():
    from app.db import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
