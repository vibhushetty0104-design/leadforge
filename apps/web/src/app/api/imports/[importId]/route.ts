import type { ImportDetail } from "@leadforge/shared";
import { NextResponse, type NextRequest } from "next/server";

import { apiFailureResponse, requireRouteViewer } from "@/lib/api/route";
import { orgRequest } from "@/lib/viewer";

/** Polled by the import progress view. */
export async function GET(request: NextRequest, { params }: { params: Promise<{ importId: string }> }) {
  const guard = await requireRouteViewer(request);
  if (!guard.ok) return guard.response;
  const { importId } = await params;
  const result = await orgRequest<ImportDetail>(guard.viewer, `/api/v1/imports/${encodeURIComponent(importId)}`);
  return result.ok ? NextResponse.json(result.data) : apiFailureResponse(result.error);
}
