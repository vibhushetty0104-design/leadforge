import type { MembershipRead } from "@leadforge/shared";
import type { ReactNode } from "react";

import { CreateOrganizationCard } from "@/components/auth/create-organization-card";
import { ErrorState } from "@/components/data/states";
import { requireViewer, type ReadyViewer } from "@/lib/viewer";

export type OrgViewer = ReadyViewer & { membership: MembershipRead };

/**
 * Resolve the viewer for an organization-scoped page. Returns either the viewer
 * or the UI to show instead (API error, or onboarding when there is no org yet).
 */
export async function resolveOrgViewer(): Promise<
  { ok: true; viewer: OrgViewer } | { ok: false; fallback: ReactNode }
> {
  const viewer = await requireViewer();
  if (viewer.kind === "error") {
    return { ok: false, fallback: <ErrorState title="Could not load your account" error={viewer.error} /> };
  }
  if (!viewer.membership) {
    return { ok: false, fallback: <CreateOrganizationCard /> };
  }
  return { ok: true, viewer: { ...viewer, membership: viewer.membership } };
}
