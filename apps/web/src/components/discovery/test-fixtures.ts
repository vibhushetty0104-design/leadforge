import type { ImportDetail, ImportRowRead } from "@leadforge/shared";

export function importDetail(overrides: Partial<ImportDetail> = {}): ImportDetail {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    filename: "leads.csv",
    size_bytes: 120,
    status: "draft",
    total_rows: 3,
    processed_rows: 0,
    created_count: 0,
    updated_count: 0,
    skipped_count: 0,
    invalid_count: 0,
    review_count: 0,
    warning_count: 0,
    duplicate_policy: "skip",
    validate_websites: true,
    error_message: null,
    job_id: null,
    created_at: "2026-11-06T10:00:00Z",
    started_at: null,
    finished_at: null,
    headers: ["Company", "Site", "City"],
    column_mapping: null,
    suggested_mapping: { business_name: "Company", website: "Site" },
    sample_rows: [{ Company: "Acme Dental", Site: "acme.com", City: "Leeds" }],
    preview: null,
    job: null,
    ...overrides,
  };
}

export function importRow(overrides: Partial<ImportRowRead> = {}): ImportRowRead {
  return {
    id: "22222222-2222-4222-8222-222222222222",
    row_number: 2,
    raw_data: {},
    normalized: { name: "Acme Dental" },
    errors: [],
    warnings: [],
    duplicate: null,
    outcome: "pending",
    resolution: null,
    business_id: null,
    ...overrides,
  };
}
