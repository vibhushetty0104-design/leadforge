import type { BusinessInspection } from "@leadforge/shared";
import { NextResponse, type NextRequest } from "next/server";

import { apiFailureResponse, requireRouteViewer } from "@/lib/api/route";
import { orgRequest } from "@/lib/viewer";

/** Polled by the inspection panel while a job is active. */
export async function GET(request: NextRequest, { params }: { params: Promise<{ businessId: string }> }) {
  const guard = await requireRouteViewer(request);
  if (!guard.ok) return guard.response;
  const { businessId } = await params;
  const result = await orgRequest<BusinessInspection>(
    guard.viewer,
    `/api/v1/businesses/${encodeURIComponent(businessId)}/inspection`,
  );
  return result.ok ? NextResponse.json(result.data) : apiFailureResponse(result.error);
}
