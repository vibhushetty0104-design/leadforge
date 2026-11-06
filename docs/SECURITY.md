# Security

## Reporting a vulnerability

Please do **not** open a public issue. Use GitHub's private vulnerability reporting ("Security" tab →
"Report a vulnerability") with reproduction steps. We aim to acknowledge reports within 7 days.

## Secrets

- All configuration comes from environment variables. `.env`, `.env.*` (except `.env.example`) and `*.pem`
  are git-ignored. No secret has a default value in code.
- Empty variables (`FOO=`) are treated as **unset**, never as an empty string. This prevents an empty
  `SUPABASE_JWT_SECRET` from becoming a forgeable HMAC key. A configured secret must be ≥ 32 characters.
- The Supabase **service-role key is never used** by any component. The web app only reads the public
  publishable/anon key.
- Database credentials are wrapped in `SecretStr` and never logged.

## Authentication

- The frontend uses Supabase Auth via `@supabase/ssr` (HTTP-only session cookies managed by Supabase).
- The API verifies every bearer token:
  - Asymmetric keys (RS256/ES256) are checked against `SUPABASE_URL/auth/v1/.well-known/jwks.json` (cached),
    and the legacy HS256 secret is checked when configured.
  - Each path only accepts its own algorithm (no algorithm confusion). `alg: none` is rejected.
  - `exp`, `sub`, `aud` (`authenticated`) and `iss` (`<SUPABASE_URL>/auth/v1`) are required, and
    `role` must be `authenticated`.
- If the JWKS endpoint is unreachable, the API returns 503 `auth_unavailable`. It never falls back to accepting
  the token.

## Authorization and tenant isolation

- The user identity comes **only** from the verified token's `sub`.
- The organization comes from the `X-Organization-Id` header and is accepted only after a membership lookup.
  Non-members and non-existent orgs get the same 403, so org ids cannot be probed.
- Service functions receive an `OrgContext` and filter every query by `organization_id`. Fetching another
  tenant's record by id returns 404.
- Request schemas use `extra="forbid"`, so bodies containing `organization_id`, `created_by`, `source` or
  `id` are rejected with 422.
- Destructive actions check roles (`owner`/`admin` for deletes), and every create or delete writes an
  `audit_logs` row with actor, entity and request id.
- Postgres RLS is enabled on every table with no policies (deny-by-default for Supabase's Data API).

## Input validation

- Pydantic validates all input with explicit lengths, patterns and enums. Pagination is bounded
  (`limit` ≤ 100, `offset` ≤ 10 000), so no unbounded collections are returned.
- Search terms are passed as bound parameters, and LIKE wildcards are escaped.
- The frontend mirrors the rules with Zod for instant feedback; the API remains authoritative.

## Imported URLs (implemented)

`leadforge_core.url_safety.normalize_public_url` runs on every website URL the API accepts. It:

- allows only `http`/`https` and the default ports (80/443), and rejects embedded credentials;
- rejects IP literals that are private, loopback, link-local (including `169.254.169.254`), CGNAT, multicast,
  reserved or unspecified, plus IPv6 forms embedding them (IPv4-mapped, 6to4, Teredo);
- rejects `localhost`, single-label hosts, numeric/shorthand hosts (`127.1`, `2130706433`, `0x7f000001`),
  internal suffixes (`.local`, `.internal`, `.lan`, `.home.arpa`, `.corp`, …) and cloud metadata hostnames;
- normalises IDNs to punycode, lowercases the host, drops fragments and caps length.

## Fetching websites (implemented)

All outbound requests go through `leadforge_worker.web.safe_fetch.SafeFetcher`. Validating a URL string is not
enough, because a public name can resolve to a private address or change between check and connection, so:

1. **Addresses are checked at connection time.** A custom network backend resolves the hostname, requires
   *every* answer to be public, and connects straight to a vetted IP. There is no second lookup to rebind, and
   TLS still verifies the certificate against the hostname.
2. **Redirects are followed by hand**, at most 5, and each hop is revalidated before it is requested.
3. **Time is bounded** by connect and read timeouts plus a wall-clock deadline for the whole fetch.
4. **Size is bounded** while streaming: 2 MiB of *decompressed* bytes by default, so a missing `Content-Length`
   or a gzip bomb cannot exceed it. Non-HTML responses are not read.
5. **`trust_env` is off**, so an inherited proxy setting cannot bypass the pinned backend.
6. **robots.txt is honoured.** It is treated as a limit, never as permission to reach anything restricted. A
   server error on robots.txt counts as a disallow, per RFC 9309.
7. **Requests are throttled per host** using the time of the last inspection, across all workers and
   organizations. A job inside the window is deferred without spending a retry attempt.

The worker only issues `GET` requests with a plain, honest User-Agent. It sends no cookies, and it never
submits forms, logs in, or attempts to get past CAPTCHAs or access controls. A `401`, `403` or `429` is recorded
as `blocked` and left alone.

### Data minimisation

Extraction keeps what a visitor can already see, in small capped amounts: up to 10 displayed emails and 10
telephone links, for example. Addresses in scripts and HTML comments are ignored, and findings stay on the
inspection record. They are never copied onto the business automatically.

### Remaining limits

Per-host throttling reads the last inspection, so two workers can race within one window. Concurrency is otherwise
limited by the number of workers, because each processes one job at a time. For stronger isolation, restrict the
worker's network egress at the platform level as well.

## CSV imports

- Uploads are streamed to a spooled temp file and counted as they arrive, so `Content-Length` is not trusted.
- Parsing is lazy, with limits on rows, columns and field size. Binary files and malformed quoting are rejected
  with a clear message.
- Nothing reaches `businesses` until a person confirms, and a member cannot choose an action that changes
  existing records. Updates fill blank fields only, and every update is written to the audit log.
- Exports neutralise spreadsheet formulas, because imported text is untrusted.

## Transport and headers

- API responses carry `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`,
  `Cache-Control: no-store` and a restrictive CSP. The interactive docs are disabled in production by default.
- The web app sends HSTS, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` and
  `Permissions-Policy`, and hides `X-Powered-By`.
- CORS accepts exact origins only. Wildcards are rejected at start-up, and `http://` origins are rejected in
  staging/production.
- Only `FORWARDED_ALLOW_IPS` proxies are trusted for `X-Forwarded-*`.

## Error handling

All errors use one JSON envelope with a `request_id`. Unexpected exceptions are logged server-side with a stack
trace and returned as a generic 500, so no SQL, paths or stack traces reach clients. Validation errors do not
echo input values.

## Known gaps (tracked)

- No rate limiting yet. Add it at the edge (platform or reverse proxy) or in the API before public launch.
- Route handlers in `apps/web/src/app/api` check `Origin` on mutations themselves; Server Actions rely on the
  framework's equivalent check.
- `npm audit` reports moderate advisories in development-only tooling (ESLint/openapi-typescript →
  `minimatch`). They are not part of the production bundle.
