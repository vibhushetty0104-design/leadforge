"use server";

import type {
  BulkInspectResult,
  BusinessCreate,
  BusinessRead,
  BusinessUpdate,
  DuplicateAction,
  ImportDetail,
  ImportField,
  ImportRowOutcome,
  ImportRowPage,
  ImportRowRead,
  JobRead,
  MembershipRead,
} from "@leadforge/shared";
import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { apiRequest, type ApiFailure } from "@/lib/api/client";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { businessFormSchema, organizationFormSchema } from "@/lib/validation/business";
import { ACTIVE_ORG_COOKIE, getViewer, orgRequest, type ReadyViewer } from "@/lib/viewer";

export type DuplicateDetails = { kind?: string; reason?: string; name?: string; domain?: string | null };

export type ActionResult<T = undefined> =
  | { ok: true; data: T }
  | {
      ok: false;
      message: string;
      fieldErrors?: Record<string, string>;
      code?: string;
      duplicate?: DuplicateDetails;
    };

const ORG_COOKIE_OPTIONS = {
  httpOnly: true,
  sameSite: "lax",
  secure: process.env.NODE_ENV === "production",
  path: "/",
  maxAge: 60 * 60 * 24 * 365,
} as const;

const OPTIONAL_BUSINESS_FIELDS = [
  "website_url",
  "industry",
  "city",
  "region",
  "country_code",
  "phone",
  "email",
  "description",
  "source_url",
  "notes",
] as const;

const UUID = /^[0-9a-f-]{36}$/i;

function failure(error: ApiFailure): ActionResult<never> {
  const fieldErrors: Record<string, string> = {};
  if (error.status === 422 && Array.isArray(error.details)) {
    for (const item of error.details as { loc?: unknown[]; msg?: string }[]) {
      const field = item.loc?.at(-1);
      if (typeof field === "string" && item.msg) {
        fieldErrors[field] = item.msg.replace(/^Value error, /, "");
      }
    }
  }
  return {
    ok: false,
    message: error.message,
    code: error.code,
    fieldErrors: Object.keys(fieldErrors).length ? fieldErrors : undefined,
    duplicate: error.code === "business_already_exists" ? (error.details as DuplicateDetails) : undefined,
  };
}

type OrgViewer = ReadyViewer & { membership: MembershipRead };

async function activeViewer(): Promise<{ ok: true; viewer: OrgViewer } | { ok: false; message: string }> {
  const viewer = await getViewer();
  if (viewer.kind !== "ready") return { ok: false, message: "Your session has expired. Sign in again." };
  if (!viewer.membership) return { ok: false, message: "Create or select an organization first." };
  return { ok: true, viewer: { ...viewer, membership: viewer.membership } };
}

function refreshDirectory(): void {
  revalidatePath("/leads");
  revalidatePath("/dashboard");
  revalidatePath("/discovery");
}

function parseBusiness(input: unknown) {
  const parsed = businessFormSchema.safeParse(input);
  if (parsed.success) return { ok: true as const, data: parsed.data };
  const fieldErrors: Record<string, string> = {};
  for (const issue of parsed.error.issues) {
    const key = issue.path[0];
    if (typeof key === "string") fieldErrors[key] ??= issue.message;
  }
  return {
    ok: false as const,
    result: { ok: false, message: "Please correct the highlighted fields.", fieldErrors } satisfies ActionResult<never>,
  };
}

export async function createBusinessAction(
  input: unknown,
  allowDuplicate = false,
): Promise<ActionResult<BusinessRead>> {
  const parsed = parseBusiness(input);
  if (!parsed.ok) return parsed.result;
  const session = await activeViewer();
  if (!session.ok) return { ok: false, message: session.message };

  // Send only non-empty optional fields; the API normalises and validates them.
  const body: BusinessCreate = {
    name: parsed.data.name,
    status: parsed.data.status,
    allow_duplicate: allowDuplicate,
  };
  for (const key of OPTIONAL_BUSINESS_FIELDS) {
    const value = parsed.data[key];
    if (value) body[key] = value;
  }

  const result = await orgRequest<BusinessRead>(session.viewer, "/api/v1/businesses", {
    method: "POST",
    body,
  });
  if (!result.ok) return failure(result.error);
  refreshDirectory();
  return { ok: true, data: result.data };
}

export async function updateBusinessAction(
  businessId: string,
  input: unknown,
  allowDuplicate = false,
): Promise<ActionResult<BusinessRead>> {
  if (!UUID.test(businessId)) return { ok: false, message: "Invalid business id." };
  const parsed = parseBusiness(input);
  if (!parsed.ok) return parsed.result;
  const session = await activeViewer();
  if (!session.ok) return { ok: false, message: session.message };

  // Empty optional fields are sent as null, which clears them.
  const body: BusinessUpdate = {
    name: parsed.data.name,
    status: parsed.data.status,
    allow_duplicate: allowDuplicate,
  };
  for (const key of OPTIONAL_BUSINESS_FIELDS) body[key] = parsed.data[key] || null;

  const result = await orgRequest<BusinessRead>(session.viewer, `/api/v1/businesses/${businessId}`, {
    method: "PATCH",
    body,
  });
  if (!result.ok) return failure(result.error);
  refreshDirectory();
  revalidatePath(`/leads/${businessId}`);
  return { ok: true, data: result.data };
}

export async function deleteBusinessAction(businessId: string): Promise<ActionResult> {
  if (!UUID.test(businessId)) return { ok: false, message: "Invalid business id." };
  const session = await activeViewer();
  if (!session.ok) return { ok: false, message: session.message };

  const result = await orgRequest<undefined>(session.viewer, `/api/v1/businesses/${businessId}`, {
    method: "DELETE",
  });
  if (!result.ok) return failure(result.error);
  refreshDirectory();
  return { ok: true, data: undefined };
}

export async function inspectBusinessAction(businessId: string): Promise<ActionResult<JobRead>> {
  if (!UUID.test(businessId)) return { ok: false, message: "Invalid business id." };
  const session = await activeViewer();
  if (!session.ok) return { ok: false, message: session.message };
  const result = await orgRequest<JobRead>(session.viewer, `/api/v1/businesses/${businessId}/inspect`, {
    method: "POST",
  });
  return result.ok ? { ok: true, data: result.data } : failure(result.error);
}

export async function bulkInspectAction(businessIds: string[]): Promise<ActionResult<BulkInspectResult>> {
  const session = await activeViewer();
  if (!session.ok) return { ok: false, message: session.message };
  const result = await orgRequest<BulkInspectResult>(session.viewer, "/api/v1/businesses/bulk-inspect", {
    method: "POST",
    body: { business_ids: businessIds },
  });
  return result.ok ? { ok: true, data: result.data } : failure(result.error);
}

export async function saveImportMappingAction(
  importId: string,
  mapping: Partial<Record<ImportField, string>>,
): Promise<ActionResult<ImportDetail>> {
  if (!UUID.test(importId)) return { ok: false, message: "Invalid import id." };
  const session = await activeViewer();
  if (!session.ok) return { ok: false, message: session.message };
  const result = await orgRequest<ImportDetail>(session.viewer, `/api/v1/imports/${importId}/mapping`, {
    method: "POST",
    body: { column_mapping: mapping },
  });
  return result.ok ? { ok: true, data: result.data } : failure(result.error);
}

export async function listImportRowsAction(
  importId: string,
  options: { offset?: number; outcome?: ImportRowOutcome; duplicatesOnly?: boolean },
): Promise<ActionResult<ImportRowPage>> {
  if (!UUID.test(importId)) return { ok: false, message: "Invalid import id." };
  const session = await activeViewer();
  if (!session.ok) return { ok: false, message: session.message };
  const result = await orgRequest<ImportRowPage>(session.viewer, `/api/v1/imports/${importId}/results`, {
    query: {
      limit: 25,
      offset: options.offset ?? 0,
      outcome: options.outcome,
      duplicates_only: options.duplicatesOnly ? "true" : undefined,
    },
  });
  return result.ok ? { ok: true, data: result.data } : failure(result.error);
}

export async function resolveImportRowAction(
  importId: string,
  rowId: string,
  resolution: DuplicateAction | null,
): Promise<ActionResult<ImportRowRead>> {
  if (!UUID.test(importId) || !UUID.test(rowId)) return { ok: false, message: "Invalid row." };
  const session = await activeViewer();
  if (!session.ok) return { ok: false, message: session.message };
  const result = await orgRequest<ImportRowRead>(
    session.viewer,
    `/api/v1/imports/${importId}/rows/${rowId}`,
    { method: "PATCH", body: { resolution } },
  );
  return result.ok ? { ok: true, data: result.data } : failure(result.error);
}

export async function confirmImportAction(
  importId: string,
  options: { duplicatePolicy: DuplicateAction; validateWebsites: boolean },
): Promise<ActionResult<ImportDetail>> {
  if (!UUID.test(importId)) return { ok: false, message: "Invalid import id." };
  const session = await activeViewer();
  if (!session.ok) return { ok: false, message: session.message };
  const result = await orgRequest<ImportDetail>(session.viewer, `/api/v1/imports/${importId}/confirm`, {
    method: "POST",
    body: { duplicate_policy: options.duplicatePolicy, validate_websites: options.validateWebsites },
  });
  if (!result.ok) return failure(result.error);
  revalidatePath("/discovery");
  return { ok: true, data: result.data };
}

export async function cancelImportAction(importId: string): Promise<ActionResult<ImportDetail>> {
  if (!UUID.test(importId)) return { ok: false, message: "Invalid import id." };
  const session = await activeViewer();
  if (!session.ok) return { ok: false, message: session.message };
  const result = await orgRequest<ImportDetail>(session.viewer, `/api/v1/imports/${importId}/cancel`, {
    method: "POST",
  });
  if (!result.ok) return failure(result.error);
  revalidatePath("/discovery");
  return { ok: true, data: result.data };
}

export async function createOrganizationAction(input: unknown): Promise<ActionResult<MembershipRead>> {
  const parsed = organizationFormSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, message: parsed.error.issues[0]?.message ?? "Invalid name." };
  }
  const viewer = await getViewer();
  if (viewer.kind !== "ready") return { ok: false, message: "Your session has expired. Sign in again." };

  const result = await apiRequest<MembershipRead>("/api/v1/organizations", {
    method: "POST",
    token: viewer.token,
    body: parsed.data,
  });
  if (!result.ok) return failure(result.error);
  (await cookies()).set(ACTIVE_ORG_COOKIE, result.data.organization.id, ORG_COOKIE_OPTIONS);
  revalidatePath("/", "layout");
  return { ok: true, data: result.data };
}

export async function switchOrganizationAction(organizationId: string): Promise<ActionResult> {
  const viewer = await getViewer();
  if (viewer.kind !== "ready") return { ok: false, message: "Your session has expired. Sign in again." };
  // Only organizations the API says you belong to can be selected.
  const isMember = viewer.me.memberships.some((m) => m.organization.id === organizationId);
  if (!isMember) return { ok: false, message: "You are not a member of that organization." };

  (await cookies()).set(ACTIVE_ORG_COOKIE, organizationId, ORG_COOKIE_OPTIONS);
  revalidatePath("/", "layout");
  return { ok: true, data: undefined };
}

export async function signOutAction(): Promise<void> {
  const supabase = await createSupabaseServerClient();
  if (supabase) {
    const { error } = await supabase.auth.signOut();
    if (error) console.error("[auth] sign-out failed", error);
  }
  (await cookies()).delete(ACTIVE_ORG_COOKIE);
  redirect("/login");
}
