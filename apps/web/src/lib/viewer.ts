import "server-only";

import type { MeRead, MembershipRead } from "@leadforge/shared";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { cache } from "react";

import { apiRequest, type ApiFailure, type ApiResult } from "@/lib/api/client";
import { missingConfiguration } from "@/lib/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const ACTIVE_ORG_COOKIE = "lf_org";

export type Viewer =
  | { kind: "unconfigured"; missing: string[] }
  | { kind: "anonymous" }
  | { kind: "error"; error: ApiFailure }
  | { kind: "ready"; token: string; me: MeRead; membership: MembershipRead | null };

export type ReadyViewer = Extract<Viewer, { kind: "ready" }>;

/** Resolve the signed-in user, their memberships and active organization once per request. */
export const getViewer = cache(async (): Promise<Viewer> => {
  // Always resolve per request, even when configuration is missing at build
  // time; otherwise the prerenderer would bake a static redirect into the page.
  await connection();
  const missing = missingConfiguration();
  if (missing.length > 0) return { kind: "unconfigured", missing };

  const supabase = await createSupabaseServerClient();
  if (!supabase) return { kind: "unconfigured", missing };
  const {
    data: { session },
  } = await supabase.auth.getSession();
  // The access token is verified by the API on every call; it is never trusted here.
  if (!session) return { kind: "anonymous" };

  const me = await apiRequest<MeRead>("/api/v1/me", { token: session.access_token });
  if (!me.ok) {
    return me.error.status === 401 ? { kind: "anonymous" } : { kind: "error", error: me.error };
  }

  const selected = (await cookies()).get(ACTIVE_ORG_COOKIE)?.value;
  const memberships = me.data.memberships;
  const membership =
    memberships.find((m) => m.organization.id === selected) ?? memberships[0] ?? null;
  return { kind: "ready", token: session.access_token, me: me.data, membership };
});

/** For pages inside the app shell: signed-out users go to /login. */
export async function requireViewer(): Promise<Exclude<Viewer, { kind: "anonymous" | "unconfigured" }>> {
  const viewer = await getViewer();
  if (viewer.kind === "anonymous" || viewer.kind === "unconfigured") redirect("/login");
  return viewer;
}

/** Organization-scoped API call on behalf of the current viewer. */
export async function orgRequest<T>(
  viewer: ReadyViewer & { membership: MembershipRead },
  path: string,
  options: Omit<Parameters<typeof apiRequest>[1] & object, "token" | "organizationId"> = {},
): Promise<ApiResult<T>> {
  return apiRequest<T>(path, {
    ...options,
    token: viewer.token,
    organizationId: viewer.membership.organization.id,
  });
}
