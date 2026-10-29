# CLAUDE.md — DORA Metrics Analytics Platform

Source of truth for how to build, run, test, ship, and extend this project. Read it fully before any non-trivial change. Last reviewed: 2026-10-27.

---

## 0. How to read this file

Every rule and tool choice carries one of three tags:

| Tag | Meaning | What you do |
|---|---|---|
| **[DECIDED]** | Settled and covered by an ADR in `docs/`. | Follow it. Changing it requires a new or superseding ADR. |
| **[DEFAULT]** | Recommended default for this project. | Follow it unless you have a concrete reason; record the reason in the PR or an ADR. |
| **[PROPOSED]** | Good idea not yet agreed. | Do **not** implement. Propose it, get a yes, write the ADR first. |

If the repo and this file disagree, the repo wins. Fix this file in the same PR.

---

## 1. Mission

An analytics platform that computes and visualizes **DORA software-delivery metrics** for **academic and small-team projects**, from GitHub and GitLab data stored in PostgreSQL and surfaced in Streamlit and Grafana.

Guiding principles:

1. **Honest over impressive.** A metric that admits "I can't tell" beats a metric that always shows a number.
2. **Definitions are code and documents.** Every number can be traced to a written, versioned definition and to the raw events behind it.
3. **Built for small data.** Student teams and small teams deploy rarely and have few incidents. Statistics, defaults, and UX must hold up at small sample sizes.
4. **Team-level, not surveillance.** The product measures delivery systems, never ranks individuals.
5. **Self-hostable in one command.** `docker compose up` must give a working system.

---

## 2. What makes this project different

Most DORA products are commercial, per-seat, enterprise-oriented engineering-intelligence platforms. This project competes on **trustworthiness, transparency, and fit for small teams**, not on feature count. These are the differentiators to protect in every design decision.

| # | Differentiator | Why it matters | Status |
|---|---|---|---|
| D1 | **Definitions as versioned ADRs** (deployment, incident, tenancy, lead time, CFR) | Competitors often use opaque, vendor-defined logic. Here every definition is documented and every result records the definition version it used. | **[DECIDED]** (ADRs exist); result-level `definition_version` **[DEFAULT]** |
| D2 | **"N/A, not 0"** with typed reasons | Missing data silently becoming zero is the most common way DORA dashboards lie. We distinguish "none happened" from "can't detect". | **[DECIDED]** |
| D3 | **Strict incident-to-deployment linking** for CFR | Fuzzy time-window attribution inflates or deflates failure rates. Only explicit, auditable links count. | **[DECIDED]** |
| D4 | **Statistical rigor**: Spearman ρ, n ≥ 30, sample size shown with every number | Small teams get noisy numbers; we refuse to dress noise up as insight. | **[DECIDED]** |
| D5 | **PR-merge-to-deploy as primary lead time** | Measures the part of the pipeline a team controls after review, and is robust to messy commit histories. DORA's reference definition (commit to deploy) is shown as a labeled secondary for comparability. | **[DECIDED]** |
| D6 | **Explainability / evidence drill-down**: click any number to see the PRs, deployments, and incidents behind it, plus the link rule that matched | Builds trust; makes grading, retros, and audits possible. | **[PROPOSED]** |
| D7 | **Tenancy built for education**: institution → course/cohort → team → repository, enforced in the database (Row-Level Security) | Enables per-course reporting with hard isolation between teams. | Tenancy model **[DECIDED]**; RLS enforcement **[PROPOSED]** |
| D8 | **Current DORA model**: five metrics (incl. deployment rework rate, "failed deployment recovery time"), shown as distributions rather than elite/high/medium/low labels | Some self-hosted tools still document the older four-key model. | **[DEFAULT]** |
| D9 | **Reproducibility bundle**: export raw events + metric code version + definition versions so a result in a report can be re-derived | Valuable for academic write-ups and course assessments. | **[PROPOSED]** |
| D10 | **Dogfooding**: this repository is tenant #1; its own CI/CD emits deployments the platform measures | Continuous proof the pipeline works; credible demo. | **[PROPOSED]** |
| D11 | **GitHub and GitLab as first-class peers** | Some competitors are GitHub-centric, with GitLab support limited or in beta. | **[DEFAULT]** |
| D12 | **Anti-gaming signals** (e.g., flag deployment-frequency spikes made of trivial or empty deployments) | Goodhart's law is real in student projects. | **[PROPOSED]** |

### Market context (light survey, October 2026 — re-verify before making external claims)

| Segment | Examples | Typical gap this project targets |
|---|---|---|
| Commercial engineering-intelligence platforms | LinearB, Swarmia, Sleuth, Jellyfish, Faros AI, Waydev, Haystack | Per-seat pricing, closed metric logic, enterprise focus, always-show-a-number UX |
| Open source / self-hosted | Apache DevLake (flexible, but you maintain it), Middleware (self-hosted, Docker Compose) | General dashboards; little emphasis on documented definitions, uncertainty, or education-specific tenancy |

Positioning sentence: *the open, auditable DORA platform for teams too small for enterprise tools and too serious for vanity dashboards.*

---

## 3. Metric specification

DORA now uses **five** metrics in two groups (throughput and instability). The older "time to restore service / MTTR" is now **failed deployment recovery time**. Use the current names in code, UI, and docs.

Default windows: rolling **28 days** and **90 days**, plus calendar week/month. Environment = production, as defined in the deployment ADR.

### 3.1 Throughput

**Deployment frequency**
- Count of successful production deployments per window; also report *deploy days* per window (useful at low frequency).
- If no deployment source is configured → `UNDETECTABLE`. If a source is healthy and nothing was deployed → `NO_EVENTS`.

**Lead time for changes — primary: PR merge → deploy [DECIDED]**
- Per merged PR: `first successful production deployment containing the PR's merge commit` − `merged_at`.
- Aggregate with **median, p75, p90** (never the mean; durations are skewed) and show `n`.
- PRs merged but not yet deployed are listed as **pending** and excluded from the distribution. They are *never* counted as 0 and never silently dropped from the evidence view.
- Handle squash, rebase, and merge-commit strategies; map PR → commits → deployment via the deployed SHA range between consecutive successful deployments to the same environment.
- Secondary, always labeled **"commit-to-deploy (DORA reference definition)"**: first commit in the PR → deploy. Never displayed unlabeled and never the headline number.

**Failed deployment recovery time**
- Per failed deployment (see CFR): `service restored timestamp` − `failed deployment timestamp`, using incident fields from the incident ADR. If the incident ADR defines the clock start differently, the ADR wins.
- Aggregate with median and p90. No failed deployments in the window → `NO_EVENTS` (never 0).

### 3.2 Instability

**Change failure rate (CFR) — strict linking [DECIDED]**
- `failed deployments / total production deployments`, always shown as counts too ("2 of 9").
- A deployment is *failed* only if at least one incident is **explicitly linked** to it under the rules in the incident-definition ADR. No time-window guessing, no "probably related", no counting unlinked incidents.
- Incident source not configured or unhealthy → `UNDETECTABLE` (N/A). Source healthy, deployments exist, zero linked incidents → a genuine `0%` with status `OK`.
- [PROPOSED] Show a Wilson score interval next to the rate; at n = 9 a bare percentage is noise.

**Deployment rework rate [PROPOSED — needs ADR]**
- `unplanned deployments / total deployments`, where *unplanned* = a deployment made in response to a strictly linked production incident (the remediation deployment).
- Distinct from CFR: CFR counts the *bad* deployment; rework rate counts the *fix* deployments.

### 3.3 The metric result contract [DEFAULT]

Every metric function returns this, never a bare number:

```python
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class MetricStatus(StrEnum):
    OK = "ok"  # computed from detectable data (value may legitimately be 0)
    NO_EVENTS = "no_events"  # source healthy, but the population is empty in this window
    UNDETECTABLE = "undetectable"  # required event source missing or unhealthy -> N/A
    INSUFFICIENT_SAMPLE = "insufficient_sample"  # below the minimum n for inferential output
    PARTIAL_DATA = "partial_data"  # computed, but known gaps (backfill incomplete, ingestion lag)


@dataclass(frozen=True)
class MetricValue:
    metric: str
    value: float | None  # None unless status in (OK, PARTIAL_DATA)
    unit: str
    status: MetricStatus
    n: int  # sample size behind the value
    window_start: datetime
    window_end: datetime
    definition_version: str  # e.g. "ADR-0003@2"; ties result to the written definition
    evidence_ids: tuple[str, ...] = ()  # rows that produced it (drill-down)
    note: str | None = None
```

Rules:
- `value is None` whenever status is `NO_EVENTS`, `UNDETECTABLE`, or `INSUFFICIENT_SAMPLE`.
- Aggregations propagate non-OK statuses; a mean/median of "N/A" is N/A, not 0.
- UI and Grafana render each status distinctly (hatched or grey, with a tooltip explaining why). Never an empty cell, never `0`.
- Changing a definition bumps `definition_version` and **recomputes** snapshots. History is never silently mutated.

### 3.4 Statistical rules [DECIDED]

- Correlations use **Spearman's ρ** (rank-based; durations and counts are skewed). Do not use Pearson on these data.
- Report a coefficient only when **n ≥ 30** paired observations (e.g., 30 weekly windows, or 30 teams). Below that: `INSUFFICIENT_SAMPLE` and "insufficient data (n = 12)".
- Always show `ρ`, p-value, `n`, and the method together. Never present a correlation without its sample size.
- Correlation is not causation; UI copy must not imply it.
- [PROPOSED] Apply a multiple-comparison correction (Holm or Benjamini–Hochberg) when many pairs are tested at once.
- Implementation: `scipy.stats.spearmanr`, wrapped in `src/dora_platform/stats/` with the n-threshold enforced inside the wrapper (not left to callers).

---

## 4. Architecture

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

Architecture rules:

1. **Raw first, derive later [DEFAULT].** Persist the provider payload unmodified in `raw_events` (deduplicated by payload hash). Normalization is a pure function of raw events, so the whole derived state can be rebuilt after a definition or bug fix.
2. **Webhooks are a hint; polling is the truth [DEFAULT].** Webhooks can be missed, duplicated, or arrive out of order. A reconciliation job re-fetches recent history on a schedule and repairs gaps.
3. **Idempotent everywhere.** Upserts keyed by `(tenant_id, provider, external_id)`. Re-running ingestion or a backfill never duplicates rows.
4. **Metric engine is pure.** `metrics/` takes plain domain objects and returns `MetricValue`. No network, no DB, no clock reads (inject `now`).
5. **Provider adapters are thin.** All GitHub/GitLab quirks live in `providers/`; the rest of the code sees a provider-neutral domain model.
6. **Dashboards never compute metrics.** They display `metric_snapshots` / API output. One implementation of every formula, in `metrics/`.

---

## 5. Toolchain

Pin the major version of everything. Check current stable versions before first install; update through Dependabot/Renovate, not by hand.

| Area | Choice | Tag |
|---|---|---|
| Language | Python 3.13 (3.12 acceptable) | [DECIDED] Python; version [DEFAULT] |
| Packaging | `uv` + `pyproject.toml` + committed `uv.lock` | [DEFAULT] |
| Web/API | FastAPI + Uvicorn (webhook receiver, REST) | [DEFAULT] |
| HTTP client | `httpx` (async), with retry/backoff | [DEFAULT] |
| Models & settings | Pydantic v2, `pydantic-settings` | [DEFAULT] |
| Database | PostgreSQL 17 (pin one major in compose) | [DECIDED] Postgres; version [DEFAULT] |
| ORM / migrations | SQLAlchemy 2.x, Alembic, `psycopg` 3 | [DEFAULT] |
| Data/stats | `pandas`, `numpy`, `scipy` | [DEFAULT] |
| Scheduling | APScheduler inside the `worker` container (no Celery/Redis until proven necessary) | [DEFAULT] |
| UI | Streamlit (primary), Grafana (time-series + ops) | [DECIDED] |
| Lint/format | `ruff` (lint + format) | [DEFAULT] |
| Types | `mypy --strict` on `metrics/`, `stats/`, `linking/`; standard mode elsewhere | [DEFAULT] |
| Tests | `pytest`, `pytest-cov`, `pytest-asyncio`, `hypothesis`, `respx` or `vcrpy`, Testcontainers (Postgres) | [DEFAULT] |
| Hooks | `pre-commit` (ruff, mypy, gitleaks, end-of-file/whitespace) | [DEFAULT] |
| Security scanning | `pip-audit`, `bandit`, `gitleaks`, Trivy (image + filesystem) | [DEFAULT] |
| Containers | Docker (multi-stage), Docker Compose; Kubernetes manifests/Helm optional later | [DEFAULT] |
| Reverse proxy / TLS | Caddy (automatic HTTPS) or Traefik | [DEFAULT] |
| CI/CD | GitHub Actions; GitLab CI mirror optional (see D11) | [DEFAULT] |
| Registry | GitHub Container Registry (GHCR) | [DEFAULT] |
| Logging | `structlog`, JSON to stdout | [DEFAULT] |
| Metrics/tracing | `prometheus-client` (+ Prometheus), OpenTelemetry optional | [DEFAULT] / [PROPOSED] |
| Error tracking | Sentry (optional, self-hostable alternative: GlitchTip) | [PROPOSED] |
| Docs | Existing `docs/` framework; MkDocs Material to publish; MADR format for ADRs; Mermaid diagrams | [DECIDED] docs/ADRs; MkDocs [PROPOSED] |
| Versioning/releases | Conventional Commits + semantic versioning + tagged releases (release-please or semantic-release) | [DEFAULT] |
| Dependency updates | Dependabot or Renovate | [DEFAULT] |

---

## 6. Repository layout (target)

Rename `dora_platform` if the package already has a different name.

```
.
├── CLAUDE.md
├── README.md
├── pyproject.toml / uv.lock
├── Makefile
├── Dockerfile
├── docker-compose.yml            # dev + self-host baseline
├── docker-compose.prod.yml       # prod overrides (resource limits, proxy, secrets)
├── .env.example                  # every variable documented; never real secrets
├── .pre-commit-config.yaml
├── .github/
│   ├── workflows/                # ci.yml, security.yml, release.yml, deploy.yml
│   ├── dependabot.yml
│   └── PULL_REQUEST_TEMPLATE.md
├── docs/
│   ├── adr/                      # deployment, incident, tenancy, metric definitions, ...
│   ├── architecture/             # diagrams, data model
│   ├── runbooks/                 # deploy, rollback, backup/restore, provider outage, rotate secrets
│   └── user/                     # how to connect a repo, read the dashboards
├── deploy/
│   ├── grafana/provisioning/     # datasources + dashboards as code
│   ├── caddy/Caddyfile
│   ├── postgres/init/            # roles (app rw, grafana ro), extensions
│   └── k8s/ or helm/             # optional
├── migrations/                   # Alembic
├── src/dora_platform/
│   ├── config.py                 # pydantic-settings; the only place env vars are read
│   ├── db/                       # engine, session, tenant context (RLS), models
│   ├── providers/                # github/, gitlab/ — clients, auth, webhook verification, mappers
│   ├── ingestion/                # raw event store, normalizers, reconcile, backfill
│   ├── domain/                   # provider-neutral dataclasses (Deployment, PullRequest, Incident, ...)
│   ├── linking/                  # strict incident↔deployment linking rules (+ evidence output)
│   ├── metrics/                  # pure metric functions returning MetricValue
│   ├── stats/                    # Spearman wrapper, intervals, sample-size guards
│   ├── api/                      # FastAPI app, routers, schemas, auth deps
│   ├── dashboards/               # Streamlit app + components
│   ├── worker.py                 # scheduler entrypoint
│   └── observability/            # logging, Prometheus, health checks
├── scripts/                      # seed demo data, one-off ops (documented, idempotent)
└── tests/
    ├── unit/                     # pure logic: metrics, stats, linking, mappers
    ├── integration/              # real Postgres via Testcontainers; RLS; migrations
    ├── contract/                 # recorded GitHub/GitLab payloads
    ├── e2e/                      # compose up → webhook → dashboard/API assertion
    └── fixtures/                 # golden datasets with hand-computed expected metrics
```

---

## 7. Data model conventions

Core tables (names indicative): `tenants`, `projects`, `repositories`, `raw_events`, `pull_requests`, `commits`, `deployments`, `deployment_commits`, `incidents`, `incident_deployment_links`, `metric_snapshots`, `ingestion_runs`, `provider_connections`.

- UUID primary keys; **every** row carries `tenant_id`.
- All timestamps `timestamptz`, stored in UTC; convert only in the presentation layer.
- Unique constraint `(tenant_id, provider, external_id)` on every provider-sourced entity.
- `incident_deployment_links` stores `rule_id`, `evidence` (JSONB), and `created_by` (system vs. manual) so every CFR attribution is auditable.
- `metric_snapshots` stores `definition_version`, `status`, `n`, window, and evidence references; unique per `(tenant_id, scope, metric, window, definition_version)`.
- Migrations only through Alembic; reversible where feasible; no hand-run DDL. Destructive migrations need an explicit PR note and a backup step in the runbook.
- Indexes on `(tenant_id, deployed_at)`, `(tenant_id, merged_at)`, `(tenant_id, started_at)`; add partitioning for `raw_events` only when row counts justify it.
- **Row-Level Security [PROPOSED, pending tenancy ADR review]:** enable RLS on every tenant table, set `app.tenant_id` per request/job with `SET LOCAL`, and policy `USING (tenant_id = current_setting('app.tenant_id')::uuid)`. The application role must **not** be the table owner or a superuser (owners bypass RLS unless `FORCE ROW LEVEL SECURITY` is set). Grafana uses a separate read-only role.

---

## 8. Provider integration

**GitHub**
- Authenticate as a **GitHub App** (not personal access tokens) with **read-only** permissions only: metadata, contents, pull requests, deployments, issues, actions.
- Verify every webhook via the `X-Hub-Signature-256` HMAC (constant-time compare) before touching the payload.
- Prefer GraphQL or conditional REST requests (ETags) to conserve rate limit; honor `Retry-After` and secondary-rate-limit responses; exponential backoff with jitter.
- Deployment signals: Deployments API / `deployment_status` events, Actions runs targeting a protected environment; releases or tags as a fallback only when the deployment ADR allows it.

**GitLab**
- Project/group access tokens with the minimum read scopes; verify the `X-Gitlab-Token` header on webhooks.
- Deployment signals: Deployments and Environments APIs. Incidents: GitLab incident-type issues. Use keyset pagination where offered.

**Incident sources**
- Defined by the incident ADR (typically labeled issues or native incidents). Optional later integrations (PagerDuty, Opsgenie) are **[PROPOSED]**.
- For academic teams with no incident tooling, a manual CSV/UI entry path is acceptable **only** if entries carry explicit deployment links, so strict linking still holds.

**General**
- Never trust payload fields blindly: validate with Pydantic models; reject unknown event shapes into a quarantine table, don't crash the worker.
- Handle out-of-order and duplicate events. Deleted/force-pushed history must not corrupt metrics; reconciliation repairs it.
- Contract tests use recorded real payloads; update fixtures when a provider changes a schema.

---

## 9. Configuration

All configuration comes from environment variables, read **only** in `config.py`. Keep `.env.example` complete and commented.

```dotenv
# --- core ---
APP_ENV=dev                    # dev | test | staging | prod
APP_VERSION=dev
LOG_LEVEL=INFO
DATABASE_URL=postgresql+psycopg://dora:change-me@db:5432/dora
POSTGRES_DB=dora
POSTGRES_USER=dora
POSTGRES_PASSWORD=change-me

# --- GitHub App ---
GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY_PATH=/run/secrets/github_app_key.pem
GITHUB_WEBHOOK_SECRET=

# --- GitLab ---
GITLAB_BASE_URL=https://gitlab.com
GITLAB_TOKEN=
GITLAB_WEBHOOK_TOKEN=

# --- metrics ---
MIN_SAMPLE_SIZE=30             # Spearman threshold [DECIDED]; do not lower
METRIC_WINDOW_DAYS=28
RECONCILE_INTERVAL_MINUTES=15

# --- ops ---
GRAFANA_ADMIN_PASSWORD=change-me
SENTRY_DSN=
```

Rules: no secret in code, images, logs, or git history. Prod secrets come from Docker/Kubernetes secrets or the host's secret manager. `.env` is gitignored. Rotating any secret is a documented runbook, not an improvisation.

---

## 10. Local development

```bash
cp .env.example .env            # then edit
make bootstrap                  # uv sync, pre-commit install
make up                         # docker compose up -d (db, migrate, api, worker, dashboard, grafana)
make seed                       # load demo tenant with golden-dataset events
make test                       # unit + integration
```

Makefile targets to maintain (keep them thin wrappers over real commands):

| Target | Does |
|---|---|
| `bootstrap` | `uv sync --frozen`, `pre-commit install` |
| `lint` / `fmt` | `ruff check .` / `ruff format .` |
| `typecheck` | `mypy src` |
| `test` | `pytest -q` (unit + integration) |
| `test-unit` / `test-int` / `test-e2e` | Selective runs |
| `cov` | Tests with coverage report; fails below thresholds |
| `migrate` / `migration m="msg"` | `alembic upgrade head` / autogenerate a revision |
| `up` / `down` / `logs` | Compose lifecycle |
| `seed` | Idempotent demo data |
| `audit` | `pip-audit`, `bandit`, `gitleaks` |
| `docs` | Build/serve docs locally |
| `ci` | Everything CI runs, locally, in the same order |

---

## 11. Docker and Compose

### Dockerfile rules [DEFAULT]

- Multi-stage build: builder installs dependencies from the lockfile; runtime stage copies only the virtualenv and `src/`.
- Pin base images (by digest in prod builds) and pin the `uv` image version.
- Run as a **non-root** user; no shell tools beyond what's needed; no secrets in layers or build args.
- Include a `HEALTHCHECK`; set `PYTHONUNBUFFERED=1`; one process per container.
- Keep the image small and reproducible: `uv sync --frozen --no-dev`.
- Scan every built image with Trivy in CI; fail on HIGH/CRITICAL with a fix available.

Reference skeleton:

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.13-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /bin/      # pin a real version
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.13-slim AS runtime
RUN useradd --system --uid 10001 --create-home app
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1
CMD ["uvicorn", "dora_platform.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

(The worker and dashboard reuse the image with a different `command`; override or disable the HEALTHCHECK for them.)

### Compose services

| Service | Purpose |
|---|---|
| `db` | PostgreSQL with a named volume and `pg_isready` healthcheck |
| `migrate` | One-shot `alembic upgrade head`; other services wait for `service_completed_successfully` |
| `api` | FastAPI: webhooks, REST, `/healthz`, `/readyz`, `/metrics` |
| `worker` | Scheduler: reconcile, backfill, snapshot recompute |
| `dashboard` | Streamlit (health at `/_stcore/health`) |
| `grafana` | Provisioned datasources/dashboards from `deploy/grafana/provisioning`; read-only DB role |
| `proxy` (prod) | Caddy/Traefik: TLS, routing, security headers, request size limits |
| `prometheus` (optional) | Scrapes `api`/`worker` for ops dashboards |

Reference skeleton (`docker-compose.yml`):

```yaml
name: dora-platform

x-app: &app
  build: .
  image: ghcr.io/<owner>/dora-platform:${APP_VERSION:-dev}
  env_file: .env
  restart: unless-stopped
  depends_on:
    migrate:
      condition: service_completed_successfully

services:
  db:
    image: postgres:17
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-dora}
      POSTGRES_USER: ${POSTGRES_USER:-dora}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./deploy/postgres/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 10

  migrate:
    build: .
    env_file: .env
    command: ["alembic", "upgrade", "head"]
    depends_on:
      db:
        condition: service_healthy
    restart: "no"

  api:
    <<: *app
    command: ["uvicorn", "dora_platform.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
    ports: ["8000:8000"]

  worker:
    <<: *app
    command: ["python", "-m", "dora_platform.worker"]
    healthcheck:
      disable: true

  dashboard:
    <<: *app
    command: ["streamlit", "run", "src/dora_platform/dashboards/app.py",
              "--server.port=8501", "--server.address=0.0.0.0"]
    ports: ["8501:8501"]

  grafana:
    image: grafana/grafana-oss:<pinned-version>
    restart: unless-stopped
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:?set GRAFANA_ADMIN_PASSWORD in .env}
    volumes:
      - grafana-data:/var/lib/grafana
      - ./deploy/grafana/provisioning:/etc/grafana/provisioning:ro
    ports: ["3000:3000"]
    depends_on:
      - db

volumes:
  pgdata:
  grafana-data:
```

Prod overrides (`docker-compose.prod.yml`): no host port publishing except the proxy; resource limits; `read_only: true` root filesystems with explicit tmpfs; Docker secrets for credentials; restart policies; log rotation; pinned image digests.

---

## 12. CI/CD

GitHub Actions. Every PR runs the full gate; `main` is always releasable.

| Stage | Contents | Blocks merge |
|---|---|---|
| 1. Static | `ruff check`, `ruff format --check`, `mypy` | Yes |
| 2. Unit | `pytest tests/unit` with coverage | Yes |
| 3. Integration | Postgres service/Testcontainers: migrations up (and down where reversible), RLS isolation, ingestion idempotency | Yes |
| 4. Security | `pip-audit`, `bandit`, `gitleaks`, dependency review | Yes |
| 5. Build | Docker build (BuildKit cache), Trivy image scan, optional SBOM | Yes |
| 6. E2E (main/nightly) | `docker compose up`, replay recorded webhooks, assert API/dashboard output against golden numbers | Yes on main |
| 7. Publish (on tag) | Push versioned image to GHCR, create release notes from Conventional Commits | — |
| 8. Deploy | Staging automatically; **production behind a manual approval** via GitHub Environments | — |
| 9. Smoke test | Hit `/healthz`, `/readyz`, one metrics endpoint post-deploy; auto-rollback on failure | — |

Quality gates [DEFAULT]: ≥ 90 % line coverage on `metrics/`, `stats/`, `linking/`; ≥ 80 % overall; zero new HIGH/CRITICAL vulnerabilities; no skipped or `xfail` tests without a linked issue.

**Dogfooding [PROPOSED]:** the deploy job creates a GitHub Deployment (with environment and status) so this platform measures its own repository as tenant #1.

Branching: short-lived feature branches off `main`, small PRs, squash-merge with a Conventional Commit title, branch protection requiring green CI and one review. If the course or team mandates Git Flow, follow it and document the mapping to environments.

---

## 13. Testing strategy

- **Golden datasets:** small hand-built event sets in `tests/fixtures/` with expected metrics computed by hand and documented. These are the regression anchor for every metric.
- **Property-based tests (Hypothesis)** for the metric engine: order-independence of events, idempotence of re-ingestion, monotonic windows, N/A propagation, "never returns 0 for undetectable".
- **Every metric** has tests for: normal case, empty input, single data point, N/A/undetectable, pending (undeployed) PRs, timezone/DST boundaries, and window edges.
- **Statistics:** tests for n = 29 vs 30 (threshold), ties, constant series, perfect correlation.
- **Linking:** each strict-link rule has positive and negative cases, including "near miss" incidents that must *not* link.
- **Contract tests:** recorded GitHub/GitLab payloads; never call live APIs in CI.
- **Integration:** real Postgres; migration up/down on empty and seeded DBs; **tenant isolation test** (tenant A can never read tenant B, through app role, Grafana role, and API).
- **Performance:** a backfill of ≥ 10k PRs finishes within an agreed budget; recompute is incremental where possible.
- **Mutation testing (optional, `mutmut`)** on `metrics/` and `linking/` to confirm tests actually bite.
- Each bug fix ships with a regression test first.

---

## 14. Security and privacy

- Threat surfaces: public webhook endpoint, provider tokens, multi-tenant data, student/personal data, dashboards.
- Webhooks: verify signatures **before** parsing; reject oversized bodies; rate-limit; replay-protect by delivery ID.
- Least privilege: read-only provider permissions; separate DB roles (migrator, app, Grafana read-only); no superuser at runtime.
- Auth for UIs: place Streamlit and Grafana behind SSO/OIDC (e.g., GitHub OAuth via `oauth2-proxy`) or the proxy's auth; never expose Grafana admin or Streamlit unauthenticated on the internet.
- Tenant isolation enforced in the database, not only in application code (see §7).
- SQL only through SQLAlchemy/parameterized queries. No string-built SQL.
- Security headers, strict CORS allow-list, TLS everywhere outside localhost.
- **Personal data minimization:** store provider login/ID and display name only if needed; do not store emails unless essential (hash if so); no per-person productivity scores or leaderboards (design stance, not just a feature gap). Treat student identities as personal data: retention limits, per-tenant export and deletion path, documented in `docs/`.
- Supply chain: lockfile, hash-pinned where practical, Dependabot/Renovate, `pip-audit` in CI, minimal base image, Trivy scans, optional SBOM and image signing (cosign) later.
- Secrets: never logged; redact tokens and payload secrets in structured logs; rotate on a schedule and on suspicion.

---

## 15. Observability and operations

- **Logs:** structured JSON (`structlog`) with `request_id`, `tenant_id`, `provider`, `delivery_id`; no secrets or full payloads at INFO.
- **Health:** `/healthz` (process up), `/readyz` (DB reachable, migrations at head, provider auth valid).
- **Prometheus metrics (ops, not DORA):** webhook receive/verify/reject counts, ingestion lag, queue depth, reconciliation duration, provider rate-limit remaining, snapshot recompute time, error rates.
- **Data-quality metrics** surfaced in the UI as a first-class feature: last successful ingestion per source, backfill completeness, count of quarantined events, `PARTIAL_DATA` reasons. This directly serves differentiator D2.
- **Alerts** (Grafana/Alertmanager): ingestion stalled, rate limit exhausted, webhook signature failure spike, DB disk > 80 %, migration pending, backup failed.
- **Backups:** nightly `pg_dump` (or managed snapshots) to off-host storage with retention; **restore tested quarterly** and documented in a runbook. Because `raw_events` is append-only, derived tables are rebuildable from it.
- **Runbooks** in `docs/runbooks/`: deploy, rollback, restore, provider outage, token rotation, rebuild-derived-state, tenant offboarding.
- **Upgrades:** migrate, then roll app containers; backward-compatible migrations (expand → migrate → contract) so a rollback never meets an incompatible schema.

---

## 16. Delivery roadmap: from scratch to production

Each phase ends with explicit exit criteria. Do not start the next phase until they are met.

**Phase 0 — Foundations**
Repo, `pyproject.toml`, uv, ruff, mypy, pytest, pre-commit, Makefile, Dockerfile, compose with `db`, CI skeleton (lint + unit), README, ADR template, `.env.example`.
*Exit:* `make ci` green locally and in GitHub Actions; `docker compose up` starts an empty, healthy stack.

**Phase 1 — Data model and ingestion**
Alembic baseline, core tables, tenant context (and RLS if approved), raw event store, GitHub App + webhook receiver, reconcile and backfill jobs, GitLab adapter, normalizers, contract fixtures.
*Exit:* a real repo backfills idempotently; re-running creates zero duplicates; tenant isolation test passes.

**Phase 2 — Metric engine**
`MetricValue` contract, strict incident linking, all five metrics, Spearman wrapper, golden datasets, property tests, `metric_snapshots` with definition versions.
*Exit:* golden-dataset numbers match hand calculations; N/A rules proven by tests; coverage gates met.

**Phase 3 — API and dashboards**
Read API, Streamlit pages (overview, per-metric detail, data quality, evidence drill-down), Grafana provisioned dashboards, distinct rendering of every `MetricStatus`.
*Exit:* a non-author can connect a repo and understand every number, including why one is N/A.

**Phase 4 — Hardening**
Auth/SSO, rate limiting, security scans in CI, Trivy gates, structured logging, Prometheus metrics, alerts, backups and a tested restore, performance budget for backfill.
*Exit:* production-readiness checklist (§17) fully ticked.

**Phase 5 — Release**
Tagged releases, GHCR images, staging → production pipeline with approval and smoke tests, docs site published, user guide, demo dataset, changelog.
*Exit:* a tagged release deploys to staging automatically and to production after approval; rollback rehearsed.

**Phase 6 — Differentiation and growth** (all **[PROPOSED]**; one ADR each)
Evidence drill-down polish (D6), reproducibility bundle (D9), course/cohort reporting and exports (D7), anti-gaming signals (D12), rework-rate ADR and UI, Wilson intervals, dogfooding dashboard (D10), optional PagerDuty/Opsgenie, optional Kubernetes/Helm packaging.

---

## 17. Production-readiness checklist

- [ ] All ADRs referenced by metric code exist, are accepted, and are linked from the docs index
- [ ] Every metric returns `MetricValue`; no code path turns missing data into `0`
- [ ] Golden-dataset, property, contract, migration, and tenant-isolation tests pass in CI
- [ ] Coverage gates met; mypy strict clean on `metrics/`, `stats/`, `linking/`
- [ ] Container runs as non-root; image scanned; no HIGH/CRITICAL fixable vulnerabilities
- [ ] Secrets only via secret store/env; `gitleaks` clean across history
- [ ] Webhook signatures verified; rate limiting and body-size limits on
- [ ] TLS terminated at the proxy; UIs behind authentication
- [ ] DB roles separated; RLS verified (if adopted); Grafana role read-only
- [ ] Backups automated, **restore tested**, runbook written
- [ ] Health/readiness endpoints, structured logs, Prometheus metrics, alerts configured
- [ ] Migrations backward-compatible; rollback rehearsed
- [ ] Data-quality view visible to users; N/A states explained in the UI
- [ ] Privacy: data retention, export, and deletion documented; no per-person scoring
- [ ] README quick start works on a clean machine in under 10 minutes
- [ ] Changelog, versioned release, and rollback instructions published

---

## 18. Conventions

**Code**
- Type hints on all public functions; small, single-purpose functions; no mutable global state.
- Keep pure logic separate from I/O (providers, DB, clock). Inject `now` and clients.
- Handle pagination, rate limits, retries, and timeouts explicitly in every provider call; no unbounded loops.
- Timestamps UTC; durations in seconds internally; human formatting only in the UI.
- Errors are specific exception types with context; never `except Exception: pass`.
- Public API responses use explicit Pydantic schemas; version the API (`/v1`).

**Commits and PRs**
- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `ci:`), imperative mood.
- PR template: what/why, linked ADR or issue, test evidence, screenshots for UI, migration notes, rollback notes.
- Docs and code change together. If a definition changes, update the ADR, the code, the dashboards, and the user docs in the same PR (or the PR is incomplete).

**ADRs**
- MADR format, numbered, immutable once accepted; supersede instead of editing. Each metric-affecting ADR states: decision, alternatives considered, consequences for small samples, and the `definition_version` it creates.

---

## 19. Working with Claude Code on this repo

- Make **small, incremental, reviewable changes**; avoid sweeping rewrites. Propose before restructuring the repo or scaffolding large new modules.
- Briefly explain the reasoning behind changes, especially anything touching metric definitions, linking rules, or statistics.
- **Before touching metric logic:** read the relevant ADR and the tests; after: run `make ci`.
- If a request conflicts with a **[DECIDED]** item, say so before proceeding. If it would require a **[PROPOSED]** item, ask first and draft the ADR rather than the code.
- State assumptions explicitly when something is ambiguous; ask at most one focused question when blocked.
- Definition of done for any task: tests added/updated and passing, lint and types clean, docs/ADRs updated, no new warnings, migration included if the schema changed, `.env.example` updated if config changed.
- Never run destructive commands (dropping volumes, rewriting history, force-pushing, deleting migrations) without explicit confirmation.
- Don't invent provider API behavior from memory: check the current provider docs or recorded payloads, and add a contract fixture.

---

## 20. Never do this

- Convert missing, undetectable, or pending data into `0`, or average over N/A values as if they were zero.
- Link incidents to deployments by proximity, guesswork, or "most recent deploy before the incident".
- Report a correlation with n < 30, a correlation without `n`, or use Pearson on duration or count data.
- Present commit-to-deploy lead time unlabeled or as the headline number.
- Compute a metric formula anywhere except `metrics/` (no SQL-only or dashboard-only re-implementations).
- Query tenant data without tenant context, or run the app with a superuser or table-owner DB role.
- Trust webhook payloads before signature verification.
- Hard-code secrets, commit `.env`, or log tokens.
- Add per-person rankings, leaderboards, or individual productivity scoring.
- Call live GitHub/GitLab APIs from tests.
- Mutate historical snapshots when a definition changes; recompute under a new `definition_version` instead.
- Add heavyweight infrastructure (Kafka, Celery/Redis, microservices) without an ADR showing the simple design failed.
