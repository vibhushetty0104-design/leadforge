# Deployment

The target is a zero-cost footprint on free tiers. Free-tier limits change, so check each provider's current terms.

| Piece | Suggested host | Notes |
| --- | --- | --- |
| Postgres and Auth | Supabase (free) | One project provides both |
| Web | Vercel (Hobby) or any container host | `apps/web/Dockerfile` for containers |
| API | Render, Fly.io, Railway, Cloud Run, … | `services/api/Dockerfile` |
| Worker | Same as API, as a background/worker service | `services/worker/Dockerfile`; needs no inbound port |

## 1. Supabase

1. Create a project. Note the **Project URL** and the **publishable (anon) key** under *Project Settings → API*.
   Do not use or copy the service-role key.
2. Under *Authentication → URL Configuration*, set the Site URL to your web URL and add
   `https://<web-host>/auth/callback` to the redirect URLs (plus `http://localhost:3000/auth/callback` for
   local development).
3. Under *Project Settings → Database*, copy a connection string. For serverless or many short connections,
   use the **pooler** URL. LEADFORGE disables prepared statements, so the transaction pooler (port 6543)
   works.
4. Signing keys: new projects use asymmetric JWT signing keys, verified via JWKS with no secret needed. If
   your project still uses the legacy shared secret, set `SUPABASE_JWT_SECRET`.

## 2. Database migrations

From a machine with the repo and Python installed:

```bash
pip install -e packages/core
export DATABASE_URL="postgresql://…"      # PowerShell: $env:DATABASE_URL="…"
alembic -c database/alembic.ini upgrade head
```

Or run the API image as a one-off: `docker run --rm -e DATABASE_URL=… leadforge-api alembic -c database/alembic.ini upgrade head`.

Optional, Supabase only: paste `database/supabase/policies.sql` into the SQL editor. It links `profiles` to
`auth.users` and adds read-only membership policies.

## 3. API

Environment:

```
ENVIRONMENT=production
DATABASE_URL=postgresql://…
SUPABASE_URL=https://<ref>.supabase.co
CORS_ALLOWED_ORIGINS=https://<web-host>
FORWARDED_ALLOW_IPS=<your platform's proxy IPs, or * if the API is only reachable through it>
LOG_JSON=true
```

Build from the repository root with `services/api/Dockerfile`. The container listens on `$PORT` (default 8000),
and the health check path is `/health`. In production the API refuses to start without an `https://`
`SUPABASE_URL`, and it rejects wildcard or `http://` CORS origins.

## 4. Worker

Same `DATABASE_URL` and `ENVIRONMENT`. The worker now processes imports and fetches websites, so imports stay
`queued` until one is running. It needs outbound HTTP and HTTPS. Where your platform allows it, block egress to
private ranges as well. Build with `services/worker/Dockerfile`. Allow a graceful stop period
(≥ 60 s) so the current job can finish on deploys. Run more replicas to scale; `SKIP LOCKED` keeps them from
colliding.

## 5. Web

**Vercel:** import the repository, set *Root Directory* to `apps/web` (Vercel detects the npm workspace), and set:

```
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=<publishable/anon key>
API_BASE_URL=https://<api-host>
```

CSV uploads pass through this app. Vercel limits request bodies to about 4.5 MB, which is why
`IMPORT_MAX_UPLOAD_BYTES` defaults to 4 MB. On a container host you can raise it, along with `MAX_UPLOAD_BYTES` in
`apps/web/src/lib/csv.ts`.

**Container:** build `apps/web/Dockerfile` and supply the same variables at runtime. They are read per request,
not baked in at build time.

## Local development with the Supabase CLI (optional)

`supabase start` runs Auth locally (default `http://127.0.0.1:54321`) and prints a publishable key and a JWT
secret. Use those for `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` and (for the API) `SUPABASE_JWT_SECRET`.
`scripts/mint_dev_token.py` can then mint short-lived tokens for calling the API with curl. It refuses to run
outside development.

## Checklist before going live

- [ ] `ENVIRONMENT=production` on API and worker
- [ ] HTTPS everywhere; CORS lists only your web origin
- [ ] Supabase redirect URLs restricted to your domains
- [ ] Migrations applied; `alembic -c database/alembic.ini check` reports no drift
- [ ] Rate limiting configured at the edge (not yet built into the API)
- [ ] Database backups enabled (Supabase free tier has limited backups; consider scheduled `pg_dump`)
