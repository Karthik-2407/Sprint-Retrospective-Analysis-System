# DORA Metrics Analytics Platform

An analytics platform that computes and visualizes **DORA software-delivery metrics** for **academic and small-team projects**, from GitHub and GitLab data stored in PostgreSQL and surfaced in Streamlit and Grafana.

## Quick Start (< 10 minutes)

### Prerequisites
- Docker and Docker Compose
- Make (optional, for convenience commands)
- uv (for local development without Docker)

### 1. Clone and Configure
```bash
git clone <repository-url>
cd dora-platform
cp .env.example .env
# Edit .env with your settings (at minimum, change default passwords)
```

### 2. Start the Stack
```bash
make up
# or: docker compose up -d
```

This starts:
- **PostgreSQL** (port 5432)
- **API** (FastAPI, port 8000) — health at `http://localhost:8000/healthz`
- **Worker** (APScheduler for reconciliation/backfill)
- **Dashboard** (Streamlit, port 8501) — `http://localhost:8501`
- **Grafana** (port 3000) — `http://localhost:3000` (admin/change-me)

### 3. Verify Health
```bash
curl http://localhost:8000/healthz
# {"status": "ok"}

curl http://localhost:8000/readyz
# {"status": "ready"}
```

### 4. Load Demo Data (Optional)
```bash
make seed
# or: python scripts/seed.py
```

### 5. Run Tests
```bash
make test
# or: pytest -q
```

### 6. Stop the Stack
```bash
make down
# or: docker compose down
```

## Development Workflow

### Local Development (without Docker)
```bash
make bootstrap    # Install deps + pre-commit hooks
make lint         # Run ruff linter
make fmt          # Run ruff formatter
make typecheck    # Run mypy
make test         # Run all tests
make ci           # Full CI pipeline (lint + typecheck + test + audit)
```

### Database Migrations
```bash
make migrate                 # Apply migrations
make migration m="message"   # Create new migration
```

### View Logs
```bash
make logs
```

## Architecture

```
GitHub / GitLab
   │  webhooks (fast path)        │  scheduled reconciliation + backfill (truth path)
   ▼                              ▼
┌────────────────────────────────────────────┐
│ api (FastAPI): webhook receiver, REST API   │──┐
│ worker: pollers, backfill, recompute jobs   │  │  verify signature → store raw event → enqueue
└────────────────────────────────────────────┘  │
                                                ▼
                         PostgreSQL ── raw_events (append-only JSONB)
                                    ── normalized tables (PRs, commits, deployments, incidents, links)
                                    ── metric_snapshots (versioned by definition)
                                                │
                    ┌───────────────────────────┴──────────────────────────┐
                    ▼                                                      ▼
            Streamlit (primary UI)                              Grafana (time-series, ops)
                    └──────────── read-only DB role / API ────────────────┘
```

## Key Differentiators

1. **Definitions as versioned ADRs** — Every metric definition is documented and versioned
2. **"N/A, not 0"** — Missing data never becomes zero; typed reasons for undetectability
3. **Strict incident-to-deployment linking** — Only explicit, auditable links count for CFR
4. **Statistical rigor** — Spearman ρ, n ≥ 30, sample size shown with every number
5. **PR-merge-to-deploy lead time** — Measures the part of the pipeline a team controls
6. **Explainability / evidence drill-down** — Click any number to see the raw events behind it
7. **Tenancy built for education** — Institution → course/cohort → team → repository with RLS
8. **Current DORA model** — Five metrics shown as distributions, not elite/high/medium/low labels
9. **Reproducibility bundle** — Export raw events + metric code version + definition versions
10. **Dogfooding** — This repository is tenant #1; its own CI/CD emits deployments the platform measures

## Project Structure

```
.
├── CLAUDE.md                      # Governing specification
├── README.md                      # This file
├── pyproject.toml                 # Python project config
├── uv.lock                        # Locked dependencies
├── Makefile                       # Convenience commands
├── Dockerfile                     # Multi-stage container image
├── docker-compose.yml             # Dev stack
├── docker-compose.prod.yml        # Prod overrides
├── .env.example                   # Environment variable template
├── .pre-commit-config.yaml        # Pre-commit hooks
├── .github/
│   ├── workflows/ci.yml           # CI pipeline
│   ├── dependabot.yml             # Dependency updates
│   └── PULL_REQUEST_TEMPLATE.md   # PR template
├── docs/
│   ├── adr/                       # Architecture Decision Records (MADR format)
│   ├── architecture/              # Diagrams, data model
│   ├── runbooks/                  # Operational procedures
│   └── user/                      # User guides
├── deploy/
│   ├── grafana/provisioning/      # Grafana datasources/dashboards as code
│   ├── caddy/Caddyfile            # Reverse proxy config
│   ├── postgres/init/schema.sql   # Initial DB schema
│   └── k8s/                       # Kubernetes/Helm (optional)
├── migrations/                    # Alembic migrations
├── src/dora_platform/
│   ├── config.py                  # Configuration (pydantic-settings)
│   ├── db/                        # Database layer (engine, models, tenant context)
│   ├── providers/                 # GitHub/GitLab adapters (Phase 1+)
│   ├── ingestion/                 # Event ingestion, normalization (Phase 1+)
│   ├── domain/                    # Provider-neutral domain models (Phase 1+)
│   ├── linking/                   # Incident↔deployment linking (Phase 2+)
│   ├── metrics/                   # Pure metric functions (Phase 2+)
│   ├── stats/                     # Statistics utilities (Phase 2+)
│   ├── api/                       # FastAPI app, routers, schemas
│   ├── dashboards/                # Streamlit app
│   ├── worker.py                  # APScheduler worker
│   └── observability/             # Logging, metrics, health checks
├── scripts/
│   └── seed.py                    # Demo data loader
└── tests/
    ├── unit/                      # Pure logic tests
    ├── integration/               # Real Postgres tests (Testcontainers)
    ├── contract/                  # Recorded provider payloads
    ├── e2e/                       # Full stack tests
    └── fixtures/                  # Golden datasets
```

## Configuration

All configuration via environment variables (see `.env.example`). Key variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `APP_ENV` | Environment: dev, test, staging, prod |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `GITHUB_APP_ID` | GitHub App ID for authentication |
| `GITHUB_WEBHOOK_SECRET` | Secret for webhook signature verification |
| `MIN_SAMPLE_SIZE` | Minimum n for Spearman correlation (default: 30) |
| `METRIC_WINDOW_DAYS` | Default rolling window (default: 28) |
| `RECONCILE_INTERVAL_MINUTES` | Reconciliation job interval (default: 15) |

## Documentation

- **ADRs**: `docs/adr/` — Architecture Decision Records (MADR format)
- **Architecture**: `docs/architecture/` — Diagrams and data model
- **Runbooks**: `docs/runbooks/` — Deploy, rollback, backup, provider outage, secret rotation
- **User Guides**: `docs/user/` — How to connect a repo, read dashboards

## License

[Add your license here]

## Contributing

1. Read `CLAUDE.md` for project conventions
2. Follow the [Phase 0 exit criteria](CLAUDE.md#16-delivery-roadmap-from-scratch-to-production)
3. Run `make ci` before submitting PRs
4. Follow Conventional Commits for commit messages
