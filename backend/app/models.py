"""Control-plane metadata models.

These tables describe *what we observe and check* - datasets, columns, quality
checks, check runs, incidents and lineage edges. The actual warehouse tables
(customers, orders, ...) live in the observed warehouse and are introspected at
runtime, not modelled here.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Dataset(Base):
    __tablename__ = "dq_datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    source_table: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(100), default="core")
    owner: Mapped[str] = mapped_column(String(120), default="data-platform")
    description: Mapped[str] = mapped_column(Text, default="")
    # Max acceptable age (minutes) before the dataset is considered stale.
    freshness_sla_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    checks: Mapped[list["Check"]] = relationship(back_populates="dataset", cascade="all, delete-orphan")


class Check(Base):
    __tablename__ = "dq_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("dq_datasets.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    # One of: not_null, unique, accepted_values, range, freshness, row_count, schema.
    check_type: Mapped[str] = mapped_column(String(50), index=True)
    column_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Type-specific configuration (e.g. {"min": 0, "max": 100}).
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    severity: Mapped[str] = mapped_column(String(20), default="high")  # high | medium | low
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    dataset: Mapped[Dataset] = relationship(back_populates="checks")
    results: Mapped[list["CheckResult"]] = relationship(back_populates="check", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("dataset_id", "name", name="uq_check_name_per_dataset"),)


class CheckRun(Base):
    __tablename__ = "dq_check_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_checks: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    errored: Mapped[int] = mapped_column(Integer, default=0)
    trigger: Mapped[str] = mapped_column(String(40), default="manual")

    results: Mapped[list["CheckResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class CheckResult(Base):
    __tablename__ = "dq_check_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("dq_check_runs.id", ondelete="CASCADE"), index=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("dq_checks.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("dq_datasets.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)  # pass | fail | error
    observed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    rows_scanned: Mapped[int] = mapped_column(Integer, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    run: Mapped[CheckRun] = relationship(back_populates="results")
    check: Mapped[Check] = relationship(back_populates="results")


class Incident(Base):
    __tablename__ = "dq_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("dq_datasets.id", ondelete="CASCADE"), index=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("dq_checks.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    severity: Mapped[str] = mapped_column(String(20), default="high")
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open | acknowledged | resolved
    details: Mapped[str] = mapped_column(Text, default="")
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)


class LineageEdge(Base):
    __tablename__ = "dq_lineage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upstream: Mapped[str] = mapped_column(String(200), index=True)
    downstream: Mapped[str] = mapped_column(String(200), index=True)
    transformation: Mapped[str] = mapped_column(String(200), default="")

    __table_args__ = (UniqueConstraint("upstream", "downstream", name="uq_lineage_edge"),)


class AuditLog(Base):
    __tablename__ = "dq_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(120), default="system")
    action: Mapped[str] = mapped_column(String(120))
    entity: Mapped[str] = mapped_column(String(120), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
