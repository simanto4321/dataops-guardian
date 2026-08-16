"""FastAPI application: the DataOps Guardian control-plane API."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from . import profiling, warehouse
from .config import get_settings
from .db import get_session, init_db
from .models import AuditLog, Check, CheckResult, CheckRun, Dataset, Incident, LineageEdge
from .runner import run_all_checks
from .schemas import (
    CheckIn,
    CheckOut,
    CheckResultOut,
    CheckRunOut,
    DatasetOut,
    HealthSummary,
    IncidentOut,
    IncidentUpdate,
    LineageEdgeOut,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.api_title, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "dataops-guardian", "version": app.version}


@app.get("/api/summary", response_model=HealthSummary)
def summary(session: Session = Depends(get_session)) -> HealthSummary:
    total_datasets = session.scalar(select(func.count()).select_from(Dataset)) or 0
    total_checks = session.scalar(select(func.count()).select_from(Check).where(Check.enabled.is_(True))) or 0
    last_run = session.scalar(select(CheckRun).order_by(desc(CheckRun.started_at)).limit(1))
    passing = failing = 0
    if last_run:
        passing = session.scalar(
            select(func.count()).select_from(CheckResult).where(CheckResult.run_id == last_run.id, CheckResult.status == "pass")
        ) or 0
        failing = session.scalar(
            select(func.count()).select_from(CheckResult).where(CheckResult.run_id == last_run.id, CheckResult.status.in_(["fail", "error"]))
        ) or 0
    open_incidents = session.scalar(
        select(func.count()).select_from(Incident).where(Incident.status != "resolved")
    ) or 0
    scored = passing + failing
    quality_score = round(100.0 * passing / scored, 1) if scored else 100.0
    return HealthSummary(
        quality_score=quality_score,
        total_datasets=total_datasets,
        total_checks=total_checks,
        passing_checks=passing,
        failing_checks=failing,
        open_incidents=open_incidents,
        last_run_at=last_run.started_at if last_run else None,
    )


@app.get("/api/datasets", response_model=list[DatasetOut])
def list_datasets(session: Session = Depends(get_session)) -> list[Dataset]:
    return list(session.scalars(select(Dataset).order_by(Dataset.name)))


@app.get("/api/datasets/{dataset_id}/profile")
def dataset_profile(dataset_id: int, session: Session = Depends(get_session)) -> dict:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(404, "dataset not found")
    if not warehouse.table_exists(dataset.source_table):
        raise HTTPException(409, f"source table {dataset.source_table!r} missing - run the seed script")
    return profiling.profile_table(dataset.source_table)


@app.get("/api/checks", response_model=list[CheckOut])
def list_checks(session: Session = Depends(get_session)) -> list[Check]:
    return list(session.scalars(select(Check).order_by(Check.dataset_id, Check.name)))


@app.post("/api/checks", response_model=CheckOut, status_code=201)
def create_check(payload: CheckIn, session: Session = Depends(get_session)) -> Check:
    if session.get(Dataset, payload.dataset_id) is None:
        raise HTTPException(404, "dataset not found")
    check = Check(**payload.model_dump())
    session.add(check)
    session.add(AuditLog(actor="analyst", action="create_check", entity="check", payload={"name": payload.name}))
    session.commit()
    session.refresh(check)
    return check


@app.delete("/api/checks/{check_id}", status_code=204)
def delete_check(check_id: int, session: Session = Depends(get_session)) -> None:
    check = session.get(Check, check_id)
    if check is None:
        raise HTTPException(404, "check not found")
    session.delete(check)
    session.add(AuditLog(actor="analyst", action="delete_check", entity="check", payload={"id": check_id}))
    session.commit()


@app.post("/api/runs", response_model=CheckRunOut, status_code=201)
def trigger_run(session: Session = Depends(get_session)) -> CheckRun:
    return run_all_checks(session, trigger="manual", actor="analyst")


@app.get("/api/runs", response_model=list[CheckRunOut])
def list_runs(limit: int = 20, session: Session = Depends(get_session)) -> list[CheckRun]:
    return list(session.scalars(select(CheckRun).order_by(desc(CheckRun.started_at)).limit(limit)))


@app.get("/api/runs/{run_id}/results", response_model=list[CheckResultOut])
def run_results(run_id: int, session: Session = Depends(get_session)) -> list[CheckResult]:
    if session.get(CheckRun, run_id) is None:
        raise HTTPException(404, "run not found")
    return list(session.scalars(select(CheckResult).where(CheckResult.run_id == run_id)))


@app.get("/api/results/latest", response_model=list[CheckResultOut])
def latest_results(session: Session = Depends(get_session)) -> list[CheckResult]:
    last_run = session.scalar(select(CheckRun).order_by(desc(CheckRun.started_at)).limit(1))
    if last_run is None:
        return []
    return list(session.scalars(select(CheckResult).where(CheckResult.run_id == last_run.id)))


@app.get("/api/incidents", response_model=list[IncidentOut])
def list_incidents(status: str | None = None, session: Session = Depends(get_session)) -> list[Incident]:
    stmt = select(Incident).order_by(desc(Incident.last_seen))
    if status:
        stmt = stmt.where(Incident.status == status)
    return list(session.scalars(stmt))


@app.patch("/api/incidents/{incident_id}", response_model=IncidentOut)
def update_incident(incident_id: int, payload: IncidentUpdate, session: Session = Depends(get_session)) -> Incident:
    incident = session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    incident.status = payload.status
    if payload.status == "resolved" and incident.resolved_at is None:
        incident.resolved_at = datetime.now(timezone.utc)
    session.add(AuditLog(actor=payload.actor, action="update_incident", entity="incident", payload={"id": incident_id, "status": payload.status}))
    session.commit()
    session.refresh(incident)
    return incident


@app.get("/api/lineage", response_model=list[LineageEdgeOut])
def lineage(session: Session = Depends(get_session)) -> list[LineageEdge]:
    return list(session.scalars(select(LineageEdge)))
