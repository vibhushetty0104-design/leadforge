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
| 404 | `not_found`, `business_not_found`, `import_not_found`, `job_not_found` |
| 409 | `business_already_exists`, `business_has_no_website`, `organization_limit_reached`, `import_not_editable`, `import_not_mapped` |
| 413 | `import_too_large`, `import_too_many_rows` |
| 415 | `unsupported_media_type` |
| 422 | `validation_error` (`details` is a list of `{loc, msg, type}`), `import_invalid_csv`, `import_invalid_file`, `import_invalid_mapping` |
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

Query: `limit`, `offset`, `q` (name or domain contains, wildcards literal), `status`, `industry`, `country_code`,
`source`, `website_status`, `has_email`, `has_website`, `import_id`.

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

Only `name` is required; `email`, `description` and `source_url` are also accepted. `website_url` is normalised
(`https://` added, lowercased host, default port, trailing slash and fragment removed) and must be a public
destination. The submitted form is kept as `website_url_original`. A detected duplicate returns 409 with
`details.kind` (`definite` or `possible`), `reason` and `existing_id`; resend with `"allow_duplicate": true` to
keep it as a separate business. The server always sets `source` to `manual` and records the creator.

### `GET /api/v1/businesses/{business_id}` (org-scoped)

Returns 404 for unknown ids **and** for ids belonging to other organizations.

### `DELETE /api/v1/businesses/{business_id}` (org-scoped, owner/admin)

Returns 204. Cascades to contacts, audits, findings, scores, drafts and activities, and writes an audit-log
entry.

### `PATCH /api/v1/businesses/{business_id}` (org-scoped)

Send only the fields to change; `null` clears an optional field. Changing `website_url` resets `website_status`.
Duplicates are handled as in `POST`.

### `POST /api/v1/businesses/export` (org-scoped)

Body: any list filters, or `business_ids`. Returns a CSV attachment of at most 10,000 rows. Cells that could be read
as spreadsheet formulas are neutralised.

### `POST /api/v1/businesses/{business_id}/inspect` (org-scoped)

Returns 202 with the job. If one is already active for this business, that job is returned instead.

### `GET /api/v1/businesses/{business_id}/inspection` (org-scoped)

`{ inspection, active_job }`: the latest result, if any, and the running job, if any.

### `POST /api/v1/businesses/bulk-inspect` (org-scoped)

Body: `{ "business_ids": [...] }`, up to 100. Returns `queued`, `already_active`, `skipped_no_website`, `not_found`.

### `GET /api/v1/jobs/{job_id}` (org-scoped)

Status, attempts, `progress_current`, `progress_total`, `last_error` and `result`.

### `GET /api/v1/discovery/summary` (org-scoped)

Website and email coverage, counts by `website_status`, active and failed jobs, and the 5 latest imports.

## CSV imports

| Step | Endpoint |
| --- | --- |
| Upload | `POST /imports/csv?filename=leads.csv`, with the raw file as a `text/csv` body |
| Map and validate | `POST /imports/{id}/mapping` with `{ "column_mapping": { "business_name": "Company", ... } }` |
| Review rows | `GET /imports/{id}/results?outcome=invalid` or `?duplicates_only=true` |
| Decide one row | `PATCH /imports/{id}/rows/{row_id}` with `{ "resolution": "skip" \| "update" \| "create" \| null }` |
| Confirm | `POST /imports/{id}/confirm` with `{ "duplicate_policy": "skip", "validate_websites": true }` |
| Follow progress | `GET /imports/{id}` |
| History | `GET /imports` |
| Discard a draft | `POST /imports/{id}/cancel` |

Mapping fields: `business_name` (required), `website`, `country`, `city`, `category`, `email`, `phone`, `description`,
`source_url`. Nothing is written to `businesses` before confirmation. `update` fills blank fields only and requires
owner or admin. Possible duplicates without a row decision end as `needs_review`, and nothing is written for them.

Invalid names, websites and emails reject the row. Unrecognised countries, phones and source URLs leave the value
blank with a warning. Limits: `IMPORT_MAX_UPLOAD_BYTES` (4 MB) and `IMPORT_MAX_ROWS` (5,000).

## Example

```bash
TOKEN=…   # a Supabase access token
ORG=…     # from GET /api/v1/me
curl -s http://localhost:8000/api/v1/businesses?limit=10 \
  -H "Authorization: Bearer $TOKEN" -H "X-Organization-Id: $ORG"
```
