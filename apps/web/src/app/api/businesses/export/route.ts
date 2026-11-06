import { NextResponse, type NextRequest } from "next/server";

import { apiForward } from "@/lib/api/client";
import { requireRouteViewer } from "@/lib/api/route";

export async function POST(request: NextRequest) {
  const guard = await requireRouteViewer(request);
  if (!guard.ok) return guard.response;
  try {
    const response = await apiForward("/api/v1/businesses/export", {
      method: "POST",
      token: guard.viewer.token,
      organizationId: guard.viewer.membership.organization.id,
      contentType: "application/json",
      body: await request.text(),
    });
    const headers = new Headers({
      "Content-Type": response.headers.get("content-type") ?? "application/json",
    });
    const disposition = response.headers.get("content-disposition");
    if (disposition) headers.set("Content-Disposition", disposition);
    return new NextResponse(response.body, { status: response.status, headers });
  } catch (cause) {
    console.error("[export] failed", cause);
    return NextResponse.json(
      { error: { code: "api_unreachable", message: "The LEADFORGE API could not be reached." } },
      { status: 502 },
    );
  }
}
