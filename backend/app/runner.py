"""Orchestrates check execution, run history and incident lifecycle."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import checks as check_engine
from .models import AuditLog, Check, CheckResult, CheckRun, Incident


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _open_or_update_incident(session: Session, check: Check, outcome: check_engine.CheckOutcome) -> None:
    incident = session.scalar(
        select(Incident).where(Incident.check_id == check.id, Incident.status != "resolved")
    )
    if incident is None:
        session.add(
            Incident(
                dataset_id=check.dataset_id,
                check_id=check.id,
                title=f"{check.name} failed",
                severity=check.severity,
                status="open",
                details=outcome.message,
                occurrences=1,
            )
        )
    else:
        incident.last_seen = _utcnow()
        incident.occurrences += 1
        incident.details = outcome.message


def _auto_resolve_incident(session: Session, check: Check) -> None:
    incident = session.scalar(
        select(Incident).where(Incident.check_id == check.id, Incident.status != "resolved")
    )
    if incident is not None:
        incident.status = "resolved"
        incident.resolved_at = _utcnow()
        incident.details = f"{incident.details}\nAuto-resolved after a passing run."


def run_all_checks(session: Session, trigger: str = "manual", actor: str = "system") -> CheckRun:
    run = CheckRun(trigger=trigger, started_at=_utcnow())
    session.add(run)
    session.flush()

    active_checks = list(session.scalars(select(Check).where(Check.enabled.is_(True))))
    passed = failed = errored = 0

    for check in active_checks:
        outcome, duration_ms = check_engine.execute_check(
            check.check_type, check.dataset.source_table, check.column_name, check.config or {}
        )
        session.add(
            CheckResult(
                run_id=run.id,
                check_id=check.id,
                dataset_id=check.dataset_id,
                status=outcome.status,
                observed_value=outcome.observed_value,
                rows_scanned=outcome.rows_scanned,
                rows_failed=outcome.rows_failed,
                message=outcome.message,
                duration_ms=duration_ms,
            )
        )
        if outcome.status == "pass":
            passed += 1
            _auto_resolve_incident(session, check)
        elif outcome.status == "fail":
            failed += 1
            _open_or_update_incident(session, check, outcome)
        else:
            errored += 1

    run.finished_at = _utcnow()
    run.total_checks = len(active_checks)
    run.passed, run.failed, run.errored = passed, failed, errored
    session.add(AuditLog(actor=actor, action="run_checks", entity="check_run", payload={"run_id": run.id, "trigger": trigger}))
    session.commit()
    session.refresh(run)
    return run
