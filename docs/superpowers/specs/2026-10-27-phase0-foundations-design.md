# Phase 0: Foundations — Design Spec

**Project:** DORA Metrics Analytics Platform
**Date:** 2026-10-27
**Status:** Draft — awaiting review

---

## 1. Overview

This spec defines the Phase 0 foundations for the DORA Metrics Analytics Platform. Phase 0 establishes the repository structure, tooling, containerization, CI/CD skeleton, and a working `docker compose up` that starts an empty but healthy stack (PostgreSQL, API, Worker, Streamlit Dashboard, Grafana).

**Exit Criteria (from CLAUDE.md §16):**
- `make ci` passes locally and in GitHub Actions
- `docker compose up` starts an empty, healthy stack (all services healthy)

---

## 2. Scope

### In Scope
- Repository structure and configuration files
- Python packaging with `uv` + `pyproject.toml`
- Code quality tooling: `ruff`, `mypy`, `pytest`, `pre-commit`
- `Makefile` with all targets from CLAUDE.md §10
- Multi-stage `Dockerfile` (non-root, healthcheck, pinned base/uv)
- `docker-compose.yml` (dev stack: db, migrate, api, worker, dashboard, grafana)
- `docker-compose.prod.yml` (prod overrides)
- `.env.example` with all variables documented
- GitHub Actions CI skeleton (lint + unit tests)
- README with quick-start guide (< 10 min)
- ADR template and `docs/` directory structure
- Alembic migration setup with initial schema SQL
- Minimal application skeleton: config, DB engine, FastAPI app with health endpoints, APScheduler worker, Streamlit dashboard, observability basics

### Out of Scope
- Any business logic (ingestion, metrics, linking, providers)
- Real GitHub/GitLab integration (mock provider only)
- Authentication/SSO
- Metric computation
- Grafana dashboard content
- Data seeding beyond demo tenant scaffolding

---

## 3. Technical Decisions

| Decision | Value | Rationale |
|----------|-------|-----------|
| **Package name** | `dora_platform` | Matches CLAUDE.md §6 |
| **Python version** | 3.13-slim | CLAUDE.md §5 [DECIDED] |
| **uv version** | Latest stable (pinned at scaffold) | CLAUDE.md §5 [DEFAULT] |
| **Local auth** | Mock/fake provider | Zero-config `make up`; real adapters in Phase 1 |
| **DB init** | SQL file (`deploy/postgres/init/schema.sql`) + Alembic | Instant dev DB + versioned migrations |
| **CI platform** | GitHub Actions | CLAUDE.md §12 |
| **Database** | PostgreSQL 17 | CLAUDE.md §5 [DECIDED] |
| **ORM** | SQLAlchemy 2.x async + Alembic | CLAUDE.md §5 [DEFAULT] |
| **API framework** | FastAPI + Uvicorn | CLAUDE.md §5 [DEFAULT] |
| **Scheduler** | APScheduler (no Celery/Redis) | CLAUDE.md §5 [DEFAULT] |
| **Primary UI** | Streamlit | CLAUDE.md §5 [DECIDED] |
| **Ops UI** | Grafana | CLAUDE.md §5 [DECIDED] |
| **Logging** | structlog JSON | CLAUDE.md §5 [DEFAULT] |
| **Metrics** | prometheus-client | CLAUDE.md §5 [DEFAULT] |
| **Lint/Format** | ruff | CLAUDE.md §5 [DEFAULT] |
| **Type checking** | mypy (strict on metrics/stats/linking) | CLAUDE.md §5 [DEFAULT] |
| **Tests** | pytest + pytest-asyncio + Testcontainers | CLAUDE.md §5 [DEFAULT] |

---

## 4. Repository Structure

```
.
├── CLAUDE.md                          # Copy of the governing spec
├── README.md                          # Quick start + overview
├── pyproject.toml                     # Project metadata, dependencies, tool config
├── uv.lock                            # Locked dependencies (generated)
├── Makefile                           # All targets from CLAUDE.md §10
├── Dockerfile                         # Multi-stage, non-root, healthcheck
├── docker-compose.yml                 # Dev stack
├── docker-compose.prod.yml            # Prod overrides
├── .env.example                       # All vars documented, no secrets
├── .pre-commit-config.yaml            # ruff, mypy, gitleaks, whitespace
├── .github/
│   ├── workflows/ci.yml               # Lint + unit tests
│   ├── dependabot.yml                 # Dependency updates
│   └── PULL_REQUEST_TEMPLATE.md       # PR template
├── docs/
│   ├── adr/
│   │   └── template.md                # MADR format template
│   ├── architecture/                  # Diagrams, data model (empty)
│   ├── runbooks/                      # Deploy, rollback, backup, etc. (empty)
│   └── user/                          # User guides (empty)
├── deploy/
│   ├── grafana/provisioning/
│   │   ├── datasources/datasource.yaml
│   │   └── dashboards/dashboard.yaml
│   ├── caddy/Caddyfile                # Reverse proxy config
│   ├── postgres/init/
│   │   └── schema.sql                 # Initial schema for dev DB
│   └── k8s/                           # Placeholder for K8s/Helm
├── migrations/                        # Alembic
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                      # Empty initially
├── src/dora_platform/
│   ├── __init__.py
│   ├── config.py                      # pydantic-settings, single env source
│   ├── db/
│   │   ├── __init__.py
│   │   ├── engine.py                  # SQLAlchemy async engine, session
│   │   ├── models.py                  # Core tables: tenants, projects, repositories
│   │   └── tenant.py                  # RLS context helper (stub)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app, /healthz, /readyz
│   │   └── routers/
│   │       ├── __init__.py
│   │       └── health.py              # Health/readiness endpoints
│   ├── worker.py                      # APScheduler skeleton with placeholder jobs
│   ├── observability/
│   │   ├── __init__.py
│   │   ├── logging.py                 # structlog JSON config
│   │   └── metrics.py                 # prometheus-client metrics
│   └── dashboards/
│       ├── __init__.py
│       └── app.py                     # Streamlit skeleton (Overview, Data Quality)
├── scripts/
│   └── seed.py                        # Idempotent demo data loader
├── tests/
│   ├── unit/
│   │   ├── test_config.py
│   │   └── conftest.py
│   ├── integration/
│   │   ├── test_db_connection.py
│   │   └── conftest.py
│   ├── contract/                      # Empty (Phase 1)
│   ├── e2e/                           # Empty (Phase 3)
│   └── fixtures/                      # Empty (Phase 2)
└── alembic.ini                        # Alembic config
```

---

## 5. Key Component Designs

### 5.1 Configuration (`src/dora_platform/config.py`)

- Uses `pydantic-settings.BaseSettings`
- Reads **only** from environment variables (`.env` file via `env_file`)
- All settings defined as typed fields with defaults where safe
- `.env.example` documents every variable with comments
- No secrets in code, images, logs, or git history

### 5.2 Database Layer (`src/dora_platform/db/`)

- **engine.py**: Async SQLAlchemy 2.x engine, sessionmaker, `get_session` dependency
- **models.py**: Core tables with `tenant_id` UUID on every row
  - `tenants` — id, name, slug, created_at, settings (JSONB)
  - `projects` — id, tenant_id, name, slug, provider, provider_config (JSONB)
  - `repositories` — id, project_id, name, provider, external_id, url, default_branch
- **tenant.py**: `set_tenant_context(session, tenant_id)` helper for RLS (stub — logs warning if not implemented)

### 5.3 API (`src/dora_platform/api/`)

- **main.py**: FastAPI app with lifespan (startup/shutdown), CORS, structured logging middleware
- **routers/health.py**:
  - `GET /healthz` — process liveness (returns `{"status": "ok"}`)
  - `GET /readyz` — readiness (DB reachable, migrations at head, returns `{"status": "ready"}` or 503)

### 5.4 Worker (`src/dora_platform/worker.py`)

- APScheduler `AsyncIOScheduler`
- Placeholder jobs (no-op, logged):
  - `reconcile_recent` — every 15 min (configurable)
  - `backfill_historical` — daily at 02:00
  - `recompute_snapshots` — every 6 hours
- Graceful shutdown on SIGTERM

### 5.5 Observability (`src/dora_platform/observability/`)

- **logging.py**: `structlog` configured for JSON output, `request_id`, `tenant_id` context vars
- **metrics.py**: Prometheus metrics (counter for webhook receive, histogram for ingestion lag, gauge for queue depth)

### 5.6 Dashboard (`src/dora_platform/dashboards/app.py`)

- Streamlit multipage app:
  - `Overview` — placeholder metric cards
  - `Data Quality` — placeholder ingestion status table
- Configurable via `config.py` settings

### 5.7 Database Initialization (`deploy/postgres/init/schema.sql`)

- Creates tables matching `models.py` (tenants, projects, repositories)
- Creates `app` role (non-superuser), `grafana_ro` role (read-only)
- Enables `uuid-ossp` extension
- **RLS not enabled** (marked [PROPOSED] in CLAUDE.md §7)

### 5.8 Alembic (`migrations/`)

- `env.py`: Async engine, reads `DATABASE_URL` from config
- `script.py.mako`: Standard revision template
- First migration generated after scaffold (`make migration m="init schema"`)

### 5.9 Docker

- **Dockerfile**: Multi-stage (builder → runtime), non-root user (uid 10001), pinned base image digest in prod, `HEALTHCHECK` on `/healthz`
- **docker-compose.yml**: Services: `db`, `migrate`, `api`, `worker`, `dashboard`, `grafana`
  - `migrate` waits for `db` healthy, runs `alembic upgrade head`
  - `api`, `worker`, `dashboard` depend on `migrate` success
  - `grafana` provisions datasource pointing to `db` with `grafana_ro` role
- **docker-compose.prod.yml**: No host ports except proxy, resource limits, `read_only: true`, Docker secrets, pinned image digests

### 5.10 CI (`.github/workflows/ci.yml`)

- Triggers: PR, push to main
- Jobs:
  1. `static` — `ruff check`, `ruff format --check`, `mypy`
  2. `unit` — `pytest tests/unit` with coverage
  3. `build` — Docker build (BuildKit cache), Trivy scan (fail on HIGH/CRITICAL)
- All jobs must pass to merge

### 5.11 Makefile Targets

| Target | Command |
|--------|---------|
| `bootstrap` | `uv sync --frozen`, `pre-commit install` |
| `lint` | `ruff check .` |
| `fmt` | `ruff format .` |
| `typecheck` | `mypy src` |
| `test` | `pytest -q` (unit + integration) |
| `test-unit` | `pytest tests/unit -q` |
| `test-int` | `pytest tests/integration -q` |
| `cov` | `pytest --cov=src/dora_platform --cov-fail-under=80` |
| `migrate` | `alembic upgrade head` |
| `migration` | `alembic revision --autogenerate -m "$(msg)"` |
| `up` | `docker compose up -d` |
| `down` | `docker compose down` |
| `logs` | `docker compose logs -f` |
| `seed` | `python scripts/seed.py` |
| `audit` | `pip-audit`, `bandit`, `gitleaks` |
| `docs` | `mkdocs serve` (placeholder) |
| `ci` | Runs lint, typecheck, test, audit in sequence |

---

## 6. Testing Strategy (Phase 0)

| Test Type | Coverage |
|-----------|----------|
| Unit | `test_config.py` — settings load from env, defaults work, validation |
| Integration | `test_db_connection.py` — Testcontainers Postgres, engine connects, session works, migrations apply |
| Contract | None (Phase 1) |
| E2E | None (Phase 3) |

---

## 7. Dependencies (pyproject.toml)

### Runtime
- `fastapi`, `uvicorn[standard]`
- `sqlalchemy[asyncio]`, `alembic`, `psycopg[binary,pool]`
- `pydantic`, `pydantic-settings`
- `apscheduler`
- `structlog`, `prometheus-client`
- `streamlit`
- `python-dotenv` (for local .env loading)

### Dev/Tooling
- `ruff`, `mypy`, `pytest`, `pytest-asyncio`, `pytest-cov`
- `testcontainers[postgresql]`
- `pre-commit`, `gitleaks`, `pip-audit`, `bandit`
- `mkdocs-material` (for docs)

---

## 8. Security Considerations

- Non-root containers (uid 10001)
- No secrets in Dockerfile layers or build args
- `.env` gitignored; `.env.example` has placeholders only
- `gitleaks` in pre-commit and CI
- `pip-audit` + `bandit` in CI
- Trivy image scan in CI (fail on HIGH/CRITICAL with fix)
- CORS restricted to known origins (configurable)
- Structured logs redact sensitive fields

---

## 9. Open Questions / Future Work

1. **RLS enablement** — Pending tenancy ADR (CLAUDE.md §7, §17)
2. **GitHub App auth** — Phase 1; Phase 0 uses mock provider
3. **Grafana dashboard content** — Phase 3
4. **MkDocs publishing** — Phase 5
5. **Kubernetes/Helm** — Phase 6 [PROPOSED]

---

## 10. Approval

- [ ] Design reviewed and approved
- [ ] Self-review passed (no TBDs, no contradictions, scope focused)
- [ ] Ready for `writing-plans` skill invocation

---

*Generated via superpowers:brainstorming → writing-plans workflow*
