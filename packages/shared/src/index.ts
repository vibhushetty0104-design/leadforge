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

// Compile-time guarantee that the list above covers every status in the API enum.
type MissingStatus = Exclude<BusinessStatus, (typeof BUSINESS_STATUSES)[number]>;
const _exhaustive: MissingStatus extends never ? true : false = true;
void _exhaustive;

export type { components, paths } from "./api.gen";
