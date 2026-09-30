# Runbook

Operational procedures for development. Deployment, rollback, backup and restore: [`deployment.md`](deployment.md).

## Local development

```bash
# Backend (Python 3.12)
cd backend
python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                                 # defaults: SQLite, console email
alembic upgrade head
python -m app.scripts.seed_demo                      # optional: three demo organizations
uvicorn app.main:app --reload                        # http://127.0.0.1:8000/api/docs

# Frontend (Node 22)
cd frontend
npm ci
npm run dev                                          # http://localhost:5173 (proxies /api to :8000)
```

Emails are not sent in development: read them at `GET /api/v1/dev/outbox` (verification,
reset and invitation links). That route exists only when `ENVIRONMENT` is `development` or `test`.

## Full stack in containers

```bash
docker compose up --build            # web :3000, API :8000, Postgres :5432
docker compose exec backend python -m app.scripts.seed_demo
docker compose down -v               # stop and delete data
```

## Tests

| Suite | Command |
|---|---|
| Backend (SQLite) | `cd backend && pytest` |
| Backend (PostgreSQL) | `TEST_DATABASE_URL=postgresql://… TEST_MIGRATIONS_DATABASE_URL=postgresql://… pytest` |
| Backend lint/types | `ruff check app tests && ruff format --check app tests && mypy app` |
| Frontend | `cd frontend && npm run lint && npm run typecheck && npm test` |
| End-to-end | `cd frontend && E2E_PYTHON=../backend/.venv/Scripts/python npx playwright test` |
| Dependency audit | `pip-audit -r backend/requirements.txt` · `npm audit --omit=dev` |

## Database migrations

```bash
alembic revision --autogenerate -m "describe change"   # review the generated file!
alembic upgrade head
```
`tests/test_migrations.py` fails if the migration chain and the models disagree.

## Updating dependencies

Backend top-level dependencies live in `backend/requirements.in`; `requirements.txt` is the
pinned resolution. To update: in a clean venv run
`pip install --dry-run --ignore-installed --report r.json -r requirements.in`, write the
`install` entries of `r.json` as `name==version` lines (dropping Windows-only `colorama` and
`tzdata`), then run the full test suite on SQLite and PostgreSQL and `pip-audit -r requirements.txt`.

## Demo organizations

`python -m app.scripts.seed_demo [--reset]` creates three organizations flagged as demo. The
password comes from `DEMO_PASSWORD` or is generated and printed once. Demo data is labelled in
the UI and excluded from real-usage metrics via `data_origin`.
