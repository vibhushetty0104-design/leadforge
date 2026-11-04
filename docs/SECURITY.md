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

## Crawler rules (required for Phase 2)

The crawler must not ship until all of these hold:

1. Call `resolve_public_addresses(host)` **immediately before every connection**, and connect to the vetted
   IP (pinning) so a second DNS lookup cannot rebind to a private address.
2. Follow redirects manually. Re-run `normalize_public_url` and `resolve_public_addresses` for every hop, and
   cap redirects at 5.
3. Enforce connect, read and total timeouts, a maximum response size (stream and abort), and a content-type
   allow-list.
4. Limit concurrency per registrable domain and globally. Identify with an honest User-Agent and respect
   `robots.txt`.
5. Never submit forms, log in, execute purchases or follow `mailto:`/`tel:`/`javascript:` links. Playwright
   runs with downloads disabled and a fresh context per audit.
6. Run the worker without access to internal networks where the platform allows it (egress restrictions).

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
- `npm audit` reports moderate advisories in development-only tooling (ESLint/openapi-typescript →
  `minimatch`). They are not part of the production bundle.
