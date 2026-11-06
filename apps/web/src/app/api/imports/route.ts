import { NextResponse, type NextRequest } from "next/server";

import { apiForward } from "@/lib/api/client";
import { requireRouteViewer } from "@/lib/api/route";

/** Streams a CSV to the API, which enforces every limit. Nothing is buffered here. */
export async function POST(request: NextRequest) {
  const guard = await requireRouteViewer(request);
  if (!guard.ok) return guard.response;
  const filename = request.nextUrl.searchParams.get("filename") ?? "";

  try {
    const response = await apiForward(`/api/v1/imports/csv?filename=${encodeURIComponent(filename)}`, {
      method: "POST",
      token: guard.viewer.token,
      organizationId: guard.viewer.membership.organization.id,
      contentType: "text/csv",
      body: request.body,
    });
    return new NextResponse(response.body, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch (cause) {
    console.error("[imports] upload failed", cause);
    return NextResponse.json(
      { error: { code: "api_unreachable", message: "The LEADFORGE API could not be reached." } },
      { status: 502 },
    );
  }
}
