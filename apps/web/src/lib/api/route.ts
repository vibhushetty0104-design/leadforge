import "server-only";

import type { MembershipRead } from "@leadforge/shared";
import { NextResponse, type NextRequest } from "next/server";

import { getViewer, type ReadyViewer } from "@/lib/viewer";

export type RouteViewer = ReadyViewer & { membership: MembershipRead };

function jsonError(status: number, code: string, message: string): NextResponse {
  return NextResponse.json({ error: { code, message, details: null, request_id: null } }, { status });
}

/**
 * Shared guard for route handlers. Server Actions get an origin check from the
 * framework; these handlers enforce the same rule themselves for mutations.
 */
export async function requireRouteViewer(
  request: NextRequest,
): Promise<{ ok: true; viewer: RouteViewer } | { ok: false; response: NextResponse }> {
  if (request.method !== "GET") {
    const origin = request.headers.get("origin");
    if (origin && new URL(origin).host !== request.headers.get("host")) {
      return { ok: false, response: jsonError(403, "forbidden", "Cross-origin request refused.") };
    }
  }
  const viewer = await getViewer();
  if (viewer.kind !== "ready") {
    return { ok: false, response: jsonError(401, "unauthenticated", "Sign in again to continue.") };
  }
  if (!viewer.membership) {
    return { ok: false, response: jsonError(403, "no_organization", "Create an organization first.") };
  }
  return { ok: true, viewer: { ...viewer, membership: viewer.membership } };
}

export function apiFailureResponse(error: { status: number; code: string; message: string }): NextResponse {
  return jsonError(error.status || 502, error.code, error.message);
}
