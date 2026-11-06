import type { ImportField } from "@leadforge/shared";

/** Mirrors the API default. The API enforces the real limit while streaming. */
export const MAX_UPLOAD_BYTES = 4_000_000;

export function formatBytes(bytes: number): string {
  if (bytes < 1000) return `${bytes} B`;
  if (bytes < 1_000_000) return `${(bytes / 1000).toFixed(0)} KB`;
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}

/** Instant feedback before uploading. Returns a message, or null when acceptable. */
export function validateCsvFile(file: Pick<File, "name" | "size">): string | null {
  if (!file.name.toLowerCase().endsWith(".csv")) return "Choose a file ending in .csv.";
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) {
    return `This file is ${formatBytes(file.size)}. The limit is ${formatBytes(MAX_UPLOAD_BYTES)}.`;
  }
  return null;
}

export type ImportFieldInfo = { field: ImportField; label: string; hint: string; required?: boolean };

export const IMPORT_FIELDS: ImportFieldInfo[] = [
  { field: "business_name", label: "Business name", hint: "Required for every row", required: true },
  { field: "website", label: "Website", hint: "Checked and normalised; unsafe addresses are rejected" },
  { field: "country", label: "Country", hint: "Name or 2-letter code" },
  { field: "city", label: "City", hint: "" },
  { field: "category", label: "Category", hint: "Industry or business type" },
  { field: "email", label: "Email", hint: "Invalid addresses reject the row" },
  { field: "phone", label: "Phone", hint: "" },
  { field: "description", label: "Description", hint: "" },
  { field: "source_url", label: "Source URL", hint: "Where you found this business" },
];

/** Columns selected more than once; the API refuses these, so the form does too. */
export function duplicateColumns(mapping: Partial<Record<ImportField, string>>): string[] {
  const seen = new Set<string>();
  const repeated = new Set<string>();
  for (const header of Object.values(mapping)) {
    if (!header) continue;
    if (seen.has(header)) repeated.add(header);
    seen.add(header);
  }
  return [...repeated];
}
