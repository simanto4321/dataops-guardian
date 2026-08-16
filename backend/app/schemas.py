"""Pydantic request/response models for the API surface."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_table: str
    domain: str
    owner: str
    description: str
    freshness_sla_minutes: int


class CheckIn(BaseModel):
    dataset_id: int
    name: str
    check_type: str = Field(pattern="^(not_null|unique|accepted_values|range|freshness|row_count|schema)$")
    column_name: str | None = None
    config: dict = Field(default_factory=dict)
    severity: str = Field(default="high", pattern="^(high|medium|low)$")
    enabled: bool = True


class CheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    name: str
    check_type: str
    column_name: str | None
    config: dict
    severity: str
    enabled: bool


class CheckResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    check_id: int
    dataset_id: int
    status: str
    observed_value: float | None
    rows_scanned: int
    rows_failed: int
    message: str
    duration_ms: float
    created_at: datetime


class CheckRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: datetime | None
    total_checks: int
    passed: int
    failed: int
    errored: int
    trigger: str


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    check_id: int
    title: str
    severity: str
    status: str
    details: str
    first_seen: datetime
    last_seen: datetime
    resolved_at: datetime | None
    occurrences: int


class IncidentUpdate(BaseModel):
    status: str = Field(pattern="^(open|acknowledged|resolved)$")
    actor: str = "analyst"


class LineageEdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    upstream: str
    downstream: str
    transformation: str


class HealthSummary(BaseModel):
    quality_score: float
    total_datasets: int
    total_checks: int
    passing_checks: int
    failing_checks: int
    open_incidents: int
    last_run_at: datetime | None
