# API reference (v1)

Interactive OpenAPI docs are served at `/docs` (Swagger) and `/redoc` outside production. The machine-readable
schema is committed at [`packages/shared/openapi.json`](../packages/shared/openapi.json).

## Conventions

- **Base path:** `/api/v1` (except `/health`).
- **Auth:** `Authorization: Bearer <Supabase access token>` on every `/api/v1` route.
- **Tenancy:** organization-scoped routes require `X-Organization-Id: <uuid>`. The caller must be a member.
- **Request id:** send `X-Request-ID` (8–64 chars of `[A-Za-z0-9._-]`) to correlate logs. The API always
  returns one.
- **Pagination:** `limit` (1–100, default 25) and `offset` (0–10 000). Responses are
  `{ items, total, limit, offset }`, newest first.
- **Bodies:** JSON. Unknown fields are rejected (422).

### Error envelope

```json
{
  "error": {
    "code": "business_already_exists",
    "message": "A business with the domain acme.com already exists in this organization.",
    "details": { "domain": "acme.com", "existing_id": "…" },
    "request_id": "9f1c…"
  }
}
```

| Status | Codes |
| --- | --- |
| 401 | `unauthenticated` |
| 403 | `organization_access_denied`, `insufficient_role` |
| 404 | `not_found`, `business_not_found` |
| 409 | `business_already_exists`, `organization_limit_reached` |
| 422 | `validation_error` (`details` is a list of `{loc, msg, type}`) |
| 500 | `internal_error` (details only in server logs) |
| 503 | `auth_unavailable` (JWKS unreachable) |

## Endpoints

### `GET /health`

Liveness and database check. Returns 200 `{"status":"ok","version":"0.1.0","database":"ok"}`, or 503 with
`"status":"degraded"` when the database is unreachable. No auth.

### `GET /api/v1/me`

The caller's profile and memberships. Creates the profile on first sight of a new Supabase user.

### `POST /api/v1/organizations`

`{"name": "Northwind Studio"}` → 201 membership (`role: "owner"`). Each user can own at most 10 organizations.

### `GET /api/v1/dashboard/summary` (org-scoped)

Aggregates computed from live data: business counts (total, last 30 days, by status), audit counts, average
*latest* lead score (`null` when nothing is scored), active campaigns, drafts awaiting review, suppressions,
open/overdue follow-ups, job counts by status, the 5 most recent businesses, and
`organization.is_development_seed`.

### `GET /api/v1/businesses` (org-scoped)

Query: `limit`, `offset`, `q` (name or domain contains, 1–100 chars, wildcards literal), and `status`.

### `POST /api/v1/businesses` (org-scoped)

```json
{
  "name": "Riverside Dental",
  "website_url": "riverside-dental.com",
  "industry": "Dental clinic",
  "city": "Leeds",
  "region": "West Yorkshire",
  "country_code": "GB",
  "phone": "+44 113 000 0000",
  "notes": "Slow mobile site",
  "status": "new"
}
```

Only `name` is required. `website_url` is normalised (`https://` added, lowercased host, fragment removed) and
must be a public destination. `domain` is derived from it (minus `www.`) and must be unique within the
organization (409 otherwise). The server always sets `source` to `manual` and records the creator.

### `GET /api/v1/businesses/{business_id}` (org-scoped)

Returns 404 for unknown ids **and** for ids belonging to other organizations.

### `DELETE /api/v1/businesses/{business_id}` (org-scoped, owner/admin)

Returns 204. Cascades to contacts, audits, findings, scores, drafts and activities, and writes an audit-log
entry.

## Example

```bash
TOKEN=…   # a Supabase access token
ORG=…     # from GET /api/v1/me
curl -s http://localhost:8000/api/v1/businesses?limit=10 \
  -H "Authorization: Bearer $TOKEN" -H "X-Organization-Id: $ORG"
```
