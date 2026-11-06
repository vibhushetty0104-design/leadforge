import type { ImportDetail } from "@leadforge/shared";
import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ErrorState } from "@/components/data/states";
import { ImportWorkspace } from "@/components/discovery/import-workspace";
import { resolveOrgViewer } from "@/components/layout/org-gate";
import { Button } from "@/components/ui/button";
import { orgRequest } from "@/lib/viewer";

export const metadata: Metadata = { title: "Import" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function ImportPage({ params }: { params: Promise<{ importId: string }> }) {
  const { importId } = await params;
  if (!UUID.test(importId)) notFound();

  const gate = await resolveOrgViewer();
  if (!gate.ok) return gate.fallback;
  const { viewer } = gate;

  const result = await orgRequest<ImportDetail>(viewer, `/api/v1/imports/${importId}`);
  if (!result.ok) {
    if (result.error.status === 404) notFound();
    return <ErrorState title="Could not load this import" error={result.error} />;
  }
  const canUpdate = viewer.membership.role === "owner" || viewer.membership.role === "admin";

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2">
        <Link href="/discovery/imports">
          <ArrowLeft /> All imports
        </Link>
      </Button>
      <ImportWorkspace key={result.data.id} initial={result.data} canUpdate={canUpdate} />
    </div>
  );
}
