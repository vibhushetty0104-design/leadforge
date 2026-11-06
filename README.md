<<<<<<< HEAD
# LEADFORGE

**Prospect intelligence and website auditing for freelance developers and digital agencies.**

LEADFORGE helps you find businesses whose websites are holding them back, prove it with measured
evidence, and run human-reviewed outreach without paying for AI APIs, scraping services or lead
databases.

> **Status: Phase 1 (foundation).** Authentication, multi-tenant data model, the business/leads API and UI,
> a live dashboard and the background-job infrastructure are in place. Website audits, scoring and outreach
> land in later phases (see [Roadmap](#roadmap)).

---

## Features

| Area | Phase 1 (now) | Later |
| --- | --- | --- |
| Leads | Add, search, filter, paginate, view and delete businesses; duplicate detection by domain; SSRF-safe URL validation | CSV import (worker job) |
| Dashboard | Live KPIs from your organization's data; seed data clearly labelled | Trends |
| Audits | Data model, job queue, honest "not yet available" UI | Playwright + BeautifulSoup checks, Lighthouse |
| Scoring | Versioned, explainable `lead_scores` model | Transparent rule-based scoring engine |
| Campaigns / CRM | Data model (campaigns, drafts, suppressions, activities) | Draft review, follow-ups, pipeline board |
| Platform | Supabase Auth, org isolation, RLS deny-by-default, audit log, structured errors, CI | Team invites, rate limiting |

**Zero runtime AI spend.** No OpenAI, Anthropic or other paid LLM APIs are called at runtime.
**No fabricated data.** Metrics are computed from real records; nothing is synthesised to look busy.

## Roadmap

1. **Phase 1 — Foundation** (this release): monorepo, auth, tenancy, schema, leads API/UI, dashboard, job queue, CI.
2. **Phase 2 — Audits & scoring**: crawler with SSRF protections, Playwright/BeautifulSoup checks, findings,
   Lighthouse, rule-based lead scoring, CSV import.
3. **Phase 3 — Outreach & CRM**: campaigns, template-based personalised drafts, approval flow, suppression
   enforcement, activity timeline, follow-up reminders, pipeline board.

## Technology stack

- **Frontend:** Next.js 16 (App Router, Cache Components), TypeScript (strict), Tailwind CSS v4, shadcn/ui-style
  components on Radix, Lucide, React Hook Form + Zod, Sonner toasts, `@supabase/ssr`.
- **Backend:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PyJWT, psycopg 3.
- **Database:** PostgreSQL 16 (Supabase-compatible, RLS enabled).
- **Worker:** Python process with a Postgres-backed queue (`FOR UPDATE SKIP LOCKED`, leases, retries).
- **Infra:** Docker Compose, GitHub Actions, Vercel-compatible frontend, container-ready API and worker.

## Architecture overview

```
Browser ──► Next.js (Vercel / container)
              │  proxy.ts refreshes the Supabase session cookie
              │  Server Components + Server Actions call the API with the user's access token
              ▼
          FastAPI  /api/v1  ── verifies Supabase JWT (JWKS or HS256) ── checks org membership
              │
              ▼
          PostgreSQL (Supabase) ◄── Worker: claims jobs with SKIP LOCKED, leases + retries
```

```
leadforge/
├── apps/web/            Next.js frontend
├── services/api/        FastAPI service (routers → services → models)
├── services/worker/     Background worker
├── packages/core/       Shared Python: settings, models, DB, URL safety, job queue
├── packages/shared/     Generated TypeScript API contract (from OpenAPI)
├── database/            Alembic migrations, dev seeds, Supabase-only SQL
├── docs/                Architecture, deployment, security, API reference
├── scripts/             OpenAPI export, dev token minting
└── .github/workflows/   CI
```

Details and the reasoning behind each decision: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Screenshots

_Placeholder: add screenshots of the dashboard, leads table and mobile navigation here._

## Local setup

### Prerequisites

- Node.js ≥ 20.9 (22 recommended) and npm
- Python ≥ 3.11
- PostgreSQL 16, via Docker (recommended) or a local install
- A Supabase project for authentication: the free tier is enough, or run Supabase locally with `supabase start`

### 1. Configure environment

```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
```

Fill in `POSTGRES_PASSWORD`, `DATABASE_URL` and `SUPABASE_URL` in `.env`, and `SUPABASE_URL`,
`SUPABASE_PUBLISHABLE_KEY` and `API_BASE_URL` in `apps/web/.env.local`. See [Environment](#environment-variables).

### 2. Start Postgres

```bash
docker compose up -d db
```

### 3. Backend

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e "packages/core[dev]" -e "services/api[dev]" -e "services/worker[dev]"
alembic -c database/alembic.ini upgrade head
python -m leadforge_api              # http://localhost:8000  (docs at /docs)
python -m leadforge_worker           # in a second terminal
```

### 4. Frontend

```bash
npm install
npm run dev                          # http://localhost:3000
```

Sign up on `/login`, then create your organization. To explore with fictional data:

```bash
python database/seeds/seed_dev.py --owner-user-id <your user id from Settings>
```

This creates a separate **Development Seed** organization. The UI labels every seed record, and seeding
refuses to run when `ENVIRONMENT` is staging or production.

## Environment variables

| Variable | Used by | Required | Notes |
| --- | --- | --- | --- |
| `DATABASE_URL` | API, worker, Alembic | yes | `postgres://` URLs are accepted |
| `SUPABASE_URL` | API, web | yes | JWKS verification and the browser auth client |
| `SUPABASE_JWT_SECRET` | API | legacy only | ≥ 32 chars; leave empty for asymmetric signing keys |
| `SUPABASE_PUBLISHABLE_KEY` | web | yes | Public anon/publishable key, never the service-role key |
| `API_BASE_URL` | web | yes | Server-side URL of the API |
| `CORS_ALLOWED_ORIGINS` | API | for browser clients | Exact origins, no wildcards |
| `ENVIRONMENT` | all | no | `production`/`staging` enable strict validation |
| `POSTGRES_PASSWORD` | Docker Compose | for compose | Local container only |
| `TEST_DATABASE_URL` | tests | no | Run the suite on Postgres (the database is wiped) |

The full annotated list is in [.env.example](.env.example) and [apps/web/.env.example](apps/web/.env.example).

## Docker

```bash
docker compose up --build                   # db, migrations, api, worker
docker compose --profile full up --build    # also the web app on :3000
```

All ports bind to `127.0.0.1`. The `migrate` service runs `alembic upgrade head` before the API and worker start.

## Testing

```bash
# Backend: SQLite by default; set TEST_DATABASE_URL to also run the Postgres-only tests
pytest packages services
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/leadforge_test pytest packages services

ruff check packages services database scripts
ruff format --check packages services database scripts
mypy packages/core/src services/api/src services/worker/src

# Frontend
npm run lint
npm run typecheck
npm run build

# Regenerate the TypeScript API contract after changing API schemas
python scripts/export_openapi.py && npm run generate:api
```

`TEST_DATABASE_URL` must be a dedicated database whose name contains `test`. The suite drops and recreates
its tables there and leaves them behind, so never run Alembic against it. To validate migrations, use:

```bash
python scripts/check_migrations.py --admin-url postgresql://user:pass@localhost:5432/postgres
```

This runs upgrade, check and downgrade in two brand-new throwaway databases and drops only those.

The Postgres-only tests cover concurrent job claiming with `SKIP LOCKED`, migration-versus-model drift,
RLS coverage and `updated_at` triggers.

## Deployment overview

- **Web:** Vercel (root directory `apps/web`), or the `apps/web/Dockerfile` image.
- **API and worker:** any container host (Render, Fly.io, Railway, Cloud Run, and similar) using the provided Dockerfiles.
- **Database and auth:** Supabase free tier. Run migrations with `alembic upgrade head`, then optionally apply
  `database/supabase/policies.sql`.

Step-by-step instructions: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Security notes

- Secrets come only from the environment; `.env*` files are git-ignored and nothing secret has a default.
- Every API request is authenticated with a verified Supabase JWT, and organization access is checked against
  membership on every call. Request bodies cannot set `organization_id` or `created_by`.
- RLS is enabled on every table with no policies, so Supabase's public Data API exposes nothing by default.
- Website URLs are validated against private, loopback, link-local and metadata destinations; the crawler
  rules for Phase 2 are specified in [docs/SECURITY.md](docs/SECURITY.md).

Report vulnerabilities privately as described in [docs/SECURITY.md](docs/SECURITY.md).

## License

[MIT](LICENSE)
=======
# leadforge
something that will make finding clients easier.. Where Every Lead Forges a New Opportunity.
>>>>>>> origin/main
