# Architecture

## Components

| Component | Path | Responsibility |
| --- | --- | --- |
| Web | `apps/web` | Next.js UI. Server Components read data and Server Actions mutate it, both through the API. |
| API | `services/api` | FastAPI. Authentication, tenancy, validation and business logic. The only writer of user-initiated data. |
| Worker | `services/worker` | Long-running process that executes background jobs from the `jobs` table. |
| Core | `packages/core` | Shared Python: settings, SQLAlchemy models, engine/session helpers, URL safety, queue, logging. |
| Shared contract | `packages/shared` | TypeScript types generated from the API's OpenAPI schema. |
| Database | `database/` | Alembic migrations, development seeds, Supabase-only SQL. |

## Request flow

1. The browser hits Next.js. `src/proxy.ts` (formerly middleware) refreshes the Supabase session cookie via
   `auth.getClaims()` and redirects anonymous visitors to `/login`.
2. A page calls `getViewer()` (`src/lib/viewer.ts`). It reads the session, then calls `GET /api/v1/me` with the
   access token. The active organization comes from the `lf_org` cookie, validated against the memberships the
   API returned.
3. Page data comes from `orgRequest()`, which sends `Authorization: Bearer <token>` and `X-Organization-Id`.
4. The API verifies the JWT (`auth.py`), confirms membership (`deps.get_org_context`), and passes an
   `OrgContext` to a service function, which scopes every query by `organization_id`.
5. Mutations are Server Actions (`src/app/actions.ts`). They validate with Zod, call the API, then
   `revalidatePath`.

The browser never calls the API directly, so the access token never reaches client JavaScript beyond Supabase's
own cookie, and the API needs no CORS for the web app. CORS is still configured with exact origins for future
clients.

## Decisions

### Monorepo layout and `packages/core`

The requested structure is kept. One addition: `packages/core` is a Python package used by both the API and the
worker. Without it, the SQLAlchemy models and the queue would be duplicated or imported across services.
`packages/shared` holds the TypeScript contract.

### Typed API contract generated from OpenAPI

`scripts/export_openapi.py` writes `packages/shared/openapi.json`, and `openapi-typescript` generates
`api.gen.ts`. The frontend imports friendly aliases from `@leadforge/shared`. CI regenerates both and fails on
any diff, so backend schema changes cannot silently break the frontend.

### Alembic owns the schema

Migrations are the only way a real schema is created or changed. Neither the API nor the worker creates tables
at start-up, and tests enforce this. `Base.metadata.create_all` appears only in `leadforge_core.testing`, which
refuses databases that are not named for tests.

Test databases and migration targets are never shared: `create_all` leaves tables behind, and `alembic upgrade`
would then fail with `DuplicateTable`. CI validates migrations in a dedicated job with its own Postgres
container, using `scripts/check_migrations.py`.

### Enums as VARCHAR + CHECK

Status and category columns use SQLAlchemy `Enum(native_enum=False, create_constraint=True)`. Values are
constrained in the database, but adding one is an ordinary constraint swap rather than `ALTER TYPE … ADD VALUE`.

### Timestamps

All timestamps are `timestamptz`, read and written through `UTCDateTime`. Naive datetimes are rejected and values
are always returned as aware UTC, including on SQLite. A `BEFORE UPDATE` trigger maintains `updated_at` even
for writes that bypass the ORM. `audit_logs` is append-only and has no `updated_at`.

### Deletion behaviour

- Deleting an **organization** cascades to all tenant data. `audit_logs.organization_id` is `SET NULL`, so
  history survives.
- Deleting a **business** cascades to contacts, audits, findings, scores, drafts and activities.
- Deleting a **profile** removes memberships. Authorship columns (`created_by` and similar) become `NULL`.
- Optional links (draft → campaign/contact, audit → job, score → audit) are `SET NULL`.

### Tenancy and Supabase RLS

Every tenant table carries a non-null `organization_id` FK; a test enforces this for all models. Migration
`0001` enables RLS on **every** table with no policies. Supabase's `anon` and `authenticated` roles therefore get
nothing through the Data API, while the backend connects as the table owner and enforces isolation in code.
`database/supabase/policies.sql` adds read-only membership policies and the `profiles → auth.users` FK, for
use when direct client reads are wanted later.

### Background jobs

The queue lives in Postgres (`packages/core/src/leadforge_core/queue.py`), so there is no Redis bill.

- **Claim:** a `MATERIALIZED` CTE selects runnable jobs with `FOR UPDATE SKIP LOCKED`, then
  `UPDATE … FROM` marks them `running`. The CTE matters: with `WHERE id IN (SELECT … LIMIT n)`, Postgres can
  re-evaluate the sub-select and claim more than `n` rows. That bug was found and fixed during Phase 1 and is
  covered by a test.
- **Lease:** each claim sets `lease_expires_at`. A heartbeat thread extends it while the handler runs. Any
  worker requeues expired leases, or fails the job once attempts are exhausted.
- **Fencing:** `complete_job` and `fail_job` only succeed for the `locked_by` holder, so a worker whose lease
  was revoked cannot overwrite the result.
- **Retries:** exponential backoff (30 s, doubling, capped at 1 h) up to `max_attempts`.
  `PermanentJobError` fails the job immediately.
- **States:** `queued → running → completed | failed`, with `attempts`, `last_error`, `result` and timestamps.
- **Shutdown:** SIGTERM/SIGINT stop new claims, the current job finishes (handlers can poll
  `ctx.should_stop()`), and the process exits.
- **Capability-based claiming:** a worker only claims job types it has handlers for. Phase 1 ships no domain
  handlers, so jobs wait in `queued` instead of failing. The worker still performs lease recovery.

### Development seed data

`database/seeds/seed_dev.py` creates one organization with `is_development_seed = true`, containing fictional
businesses on reserved `example.*` domains with `source = development_seed`. The UI shows a banner and badges
for this data. No audits or scores are seeded, because those must come from real measurements. The script
refuses to run in staging or production.

### Next.js 16 specifics

- `cacheComponents` and `partialPrefetching` are enabled. Session-dependent UI sits behind Suspense: each
  route segment has its own `loading.tsx`, so sibling navigations stay instant.
- `getViewer()` calls `connection()` first, so missing build-time configuration can never be prerendered
  into a static redirect.
- Supabase settings are runtime server env vars rather than `NEXT_PUBLIC_*`, so one image works everywhere.
  The public URL and publishable key reach the browser as props.
- `output: "standalone"` produces a self-contained server for the Docker image.

## Phase 2 plan (summary)

1. **Crawler module** (`packages/core/crawler/`): an httpx fetcher that pins resolved IPs, applies
   `resolve_public_addresses` before every hop, revalidates redirects, and enforces timeouts, a body-size cap
   and per-domain concurrency limits.
2. **Audit handler** (`website_audit`): fetch with Playwright (Chromium, no form submission or logins) and
   parse with BeautifulSoup. Write `website_audits` and `audit_findings` with evidence. Lighthouse runs as a
   separate optional step.
3. **Scoring handler** (`lead_scoring`): a deterministic, versioned rule set over findings and business
   attributes. Per-factor `breakdown` explains every score.
4. **Import handler** (`import`): CSV upload stored in the job payload, validated row by row with the same
   `BusinessCreate` rules, with a per-row error report.
5. **API and UI:** `POST /businesses/{id}/audits`, audit list and detail endpoints, a findings view, and a
   score column in the leads table.
