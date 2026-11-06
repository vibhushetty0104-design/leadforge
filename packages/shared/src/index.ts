/**
 * Public API contract for LEADFORGE clients.
 *
 * `api.gen.ts` is generated from the FastAPI OpenAPI schema
 * (`python scripts/export_openapi.py && npm run generate:api`) — do not edit it.
 * This module only gives the generated schemas friendly names.
 */
import type { components } from "./api.gen";

type Schemas = components["schemas"];

export type BusinessRead = Schemas["BusinessRead"];
export type BusinessCreate = Schemas["BusinessCreate"];
export type BusinessUpdate = Schemas["BusinessUpdate"];
export type WebsiteStatus = Schemas["WebsiteStatus"];
export type BulkInspectResult = Schemas["BulkInspectResult"];
export type BusinessExportRequest = Schemas["BusinessExportRequest"];
export type ImportBatchRead = Schemas["ImportBatchRead"];
export type ImportBatchPage = Schemas["Page_ImportBatchRead_"];
export type ImportDetail = Schemas["ImportDetail"];
export type ImportField = Schemas["ImportField"];
export type ImportStatus = Schemas["ImportStatus"];
export type ImportRowRead = Schemas["ImportRowRead"];
export type ImportRowPage = Schemas["Page_ImportRowRead_"];
export type ImportRowOutcome = Schemas["ImportRowOutcome"];
export type DuplicateAction = Schemas["DuplicateAction"];
export type InspectionRead = Schemas["InspectionRead"];
export type BusinessInspection = Schemas["BusinessInspection"];
export type DiscoverySummary = Schemas["DiscoverySummary"];
export type JobRead = Schemas["JobRead"];
export type BusinessSummary = Schemas["BusinessSummary"];
export type BusinessStatus = Schemas["BusinessStatus"];
export type RecordSource = Schemas["RecordSource"];
export type BusinessPage = Schemas["Page_BusinessRead_"];
export type DashboardSummary = Schemas["DashboardSummary"];
export type JobStatus = Schemas["JobStatus"];
export type MeRead = Schemas["MeRead"];
export type MembershipRead = Schemas["MembershipRead"];
export type OrganizationRead = Schemas["OrganizationRead"];
export type OrganizationCreate = Schemas["OrganizationCreate"];
export type MemberRole = Schemas["MemberRole"];
export type HealthResponse = Schemas["HealthResponse"];
export type ErrorResponse = Schemas["ErrorResponse"];

export const BUSINESS_STATUSES = [
  "new",
  "researching",
  "qualified",
  "contacted",
  "engaged",
  "won",
  "lost",
  "disqualified",
] as const satisfies readonly BusinessStatus[];

export const WEBSITE_STATUSES = [
  "unknown",
  "reachable",
  "unreachable",
  "blocked",
] as const satisfies readonly WebsiteStatus[];

export const RECORD_SOURCES = [
  "manual",
  "csv_import",
  "development_seed",
] as const satisfies readonly RecordSource[];

// Compile-time guarantee that the list above covers every status in the API enum.
type MissingStatus = Exclude<BusinessStatus, (typeof BUSINESS_STATUSES)[number]>;
const _exhaustive: MissingStatus extends never ? true : false = true;
void _exhaustive;

export type { components, paths } from "./api.gen";
