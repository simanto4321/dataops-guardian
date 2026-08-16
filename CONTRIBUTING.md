# Contributing

Thanks for your interest! This project favors small, well-tested changes.

## Development setup

```bash
# Backend
cd backend && python -m venv .venv && pip install -r requirements.txt
python -m app.seed && pytest -q

# Frontend
cd frontend && npm install && npm run build
```

## Guidelines

- Keep the rule engine **exception-safe** — checks must return structured `error`
  outcomes, never raise into the runner.
- Any new check type needs: an `execute_*` function, a branch in `execute_check`,
  a pydantic pattern update in `schemas.py`, and a unit test in `tests/`.
- All SQL must use bound parameters and whitelisted identifiers.
- Run `pytest -q` (backend) and `npm run build` (frontend) before opening a PR.

## Commit style

Conventional-ish, imperative mood: `add freshness sampling`, `fix duplicate count`.
