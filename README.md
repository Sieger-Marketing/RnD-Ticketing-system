# Design Operations & Ticketing Management System

An internal system for running an engineering design department: from project
intake down to individual design-task execution, measuring capacity,
efficiency, quality, rework and delivery performance along the way.

```
PROJECT → DESIGN RELEASE → PRODUCT TEMPLATE → TASK → EXECUTION
        → REVIEW → REVISION → APPROVAL → RELEASE COMPLETE → PROJECT COMPLETE
```

## Status

| Area | State |
|---|---|
| Database schema + migrations | 34 tables, 240 indexes, 65 FKs, 24 check constraints |
| Auth + RBAC | 4 roles, 55 permissions, permission-gated routes |
| Core workflow API | 114 endpoints, OpenAPI documented |
| KPI / capacity / delay / health engines | Complete, config-driven |
| Demo data | 15 users, 10 projects, 26 releases, 160 tasks, 340 time entries |
| Automated tests | 99 passing, including the full acceptance scenario |
| Frontend | Not started |

## Requirements

* Python 3.12+
* PostgreSQL 16+ (developed against 18)
* Node 20+ (for the frontend, once it exists)

## Setup

### 1. Create the database

```bash
psql -h 127.0.0.1 -U postgres -d postgres -c "CREATE ROLE designops LOGIN PASSWORD 'choose-a-password';" -c "CREATE DATABASE designops OWNER designops;"
```

### 2. Configure and install

```bash
cd backend && cp .env.example .env && python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
```

Edit `.env` and set `DATABASE_URL`, `SECRET_KEY` and `JWT_SECRET`. Generate the
secrets with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 3. Migrate and seed

```bash
cd backend && .venv/Scripts/python -m alembic upgrade head && .venv/Scripts/python seed.py --demo
```

`seed.py` takes:

| Flag | Effect |
|---|---|
| *(none)* | Bootstrap only: permissions, roles, default settings. Idempotent. |
| `--demo` | Also seed the demonstration department. Skipped if projects exist. |
| `--reset --yes` | Truncate business tables first, then reseed. Destructive. |

### 4. Run

```bash
cd backend && .venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

* API docs: <http://127.0.0.1:8000/docs>
* Health: <http://127.0.0.1:8000/health> and `/health/db`

## Demo accounts

All seeded accounts share the password in `SEED_DEFAULT_PASSWORD` (default
`Design@123`).

| Role | Email | Lands on |
|---|---|---|
| Director | `rajesh.varma@designops.dev` | Executive dashboard |
| Design Manager | `lakshmi.subramanian@designops.dev` | Manager dashboard |
| Team Lead | `suresh.balan@designops.dev` | Team lead dashboard |
| Designer | `arun.prakash@designops.dev` | My work |

Team Leads are also `nithya.raghavan@` and `imran.sheikh@`; there are ten
designers. Every address follows `firstname.lastname@designops.dev`.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest tests -q
```

Tests run against the real database and the real HTTP stack, because the things
worth proving — the workflow state machine, permission gates, KPI roll-ups —
are exactly what a mocked session would stop testing. They create their own
users and projects per run, so the suite is repeatable without wiping data.

| File | Covers |
|---|---|
| `tests/test_kpi.py` | Every KPI formula, including the "no data" cases |
| `tests/test_acceptance.py` | The full section 51 scenario, end to end |
| `tests/test_rules.py` | RBAC, data integrity, workflow and settings validation |

## Project layout

```
backend/
  app/
    core/          config, enums, security, permissions, dependencies, errors
    db/            engine, session, declarative base and shared mixins
    models/        SQLAlchemy models
    schemas/       Pydantic request/response models
    api/v1/        routers, one per module
    services/      all business logic and the KPI engine
    seed/          bootstrap and demo data
  alembic/         migrations
  tests/
```

### Where the rules live

| Concern | File |
|---|---|
| Every KPI formula | `app/services/kpi.py` |
| Capacity and utilisation | `app/services/capacity_service.py` |
| Delay detection and RAG health | `app/services/health_service.py` |
| Derived totals (never hand-entered) | `app/services/rollup_service.py` |
| Task status machine and dependencies | `app/services/task_service.py` |
| Review, revision and rework | `app/services/review_service.py` |
| Template matching and generation | `app/services/template_service.py` |
| Tunable thresholds and vocabularies | `app/services/settings_service.py` |
| Permission catalogue and role grants | `app/core/permissions.py` |

Nothing outside `kpi.py` defines a metric, and nothing outside
`rollup_service.py` writes a derived total. Thresholds, KPI weights, delay
reasons and revision categories are rows in `app_settings`, editable at runtime
through `PUT /api/settings/{key}`, not constants in code.

## Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string |
| `SECRET_KEY`, `JWT_SECRET` | Signing secrets. Never commit these. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime, default 720 |
| `FILE_STORAGE_PROVIDER`, `FILE_STORAGE_PATH` | Storage adapter selection |
| `EMAIL_PROVIDER`, `EMAIL_API_KEY`, `EMAIL_FROM` | Optional email channel |
| `FRONTEND_URL`, `BACKEND_URL` | CORS and link generation |
| `SEED_DEFAULT_PASSWORD` | Password given to seeded demo accounts |

See `backend/.env.example`. `.env` is git-ignored.
