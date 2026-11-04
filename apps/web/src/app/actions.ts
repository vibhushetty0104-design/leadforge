"use server";

import type { BusinessCreate, BusinessRead, MembershipRead } from "@leadforge/shared";
import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { apiRequest, type ApiFailure } from "@/lib/api/client";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { businessFormSchema, organizationFormSchema } from "@/lib/validation/business";
import { ACTIVE_ORG_COOKIE, getViewer, orgRequest, type ReadyViewer } from "@/lib/viewer";

export type ActionResult<T = undefined> =
  | { ok: true; data: T }
  | { ok: false; message: string; fieldErrors?: Record<string, string> };

const ORG_COOKIE_OPTIONS = {
  httpOnly: true,
  sameSite: "lax",
  secure: process.env.NODE_ENV === "production",
  path: "/",
  maxAge: 60 * 60 * 24 * 365,
} as const;

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
    fieldErrors: Object.keys(fieldErrors).length ? fieldErrors : undefined,
  };
}

async function activeViewer(): Promise<
  { ok: true; viewer: ReadyViewer & { membership: MembershipRead } } | { ok: false; message: string }
> {
  const viewer = await getViewer();
  if (viewer.kind !== "ready") return { ok: false, message: "Your session has expired. Sign in again." };
  if (!viewer.membership) return { ok: false, message: "Create or select an organization first." };
  return { ok: true, viewer: { ...viewer, membership: viewer.membership } };
}

export async function createBusinessAction(input: unknown): Promise<ActionResult<BusinessRead>> {
  const parsed = businessFormSchema.safeParse(input);
  if (!parsed.success) {
    const fieldErrors: Record<string, string> = {};
    for (const issue of parsed.error.issues) {
      const key = issue.path[0];
      if (typeof key === "string") fieldErrors[key] ??= issue.message;
    }
    return { ok: false, message: "Please correct the highlighted fields.", fieldErrors };
  }

  const session = await activeViewer();
  if (!session.ok) return { ok: false, message: session.message };

  // Send only non-empty optional fields; the API normalises and validates them.
  const body: BusinessCreate = { name: parsed.data.name, status: parsed.data.status };
  for (const key of ["website_url", "industry", "city", "region", "country_code", "phone", "notes"] as const) {
    const value = parsed.data[key];
    if (value) body[key] = value;
  }

  const result = await orgRequest<BusinessRead>(session.viewer, "/api/v1/businesses", {
    method: "POST",
    body,
  });
  if (!result.ok) return failure(result.error);
  revalidatePath("/leads");
  revalidatePath("/dashboard");
  return { ok: true, data: result.data };
}

export async function deleteBusinessAction(businessId: string): Promise<ActionResult> {
  if (!/^[0-9a-f-]{36}$/i.test(businessId)) return { ok: false, message: "Invalid business id." };
  const session = await activeViewer();
  if (!session.ok) return { ok: false, message: session.message };

  const result = await orgRequest<undefined>(session.viewer, `/api/v1/businesses/${businessId}`, {
    method: "DELETE",
  });
  if (!result.ok) return failure(result.error);
  revalidatePath("/leads");
  revalidatePath("/dashboard");
  return { ok: true, data: undefined };
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
