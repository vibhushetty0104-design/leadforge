import type { ImportBatchPage } from "@leadforge/shared";
import { History } from "lucide-react";
import type { Metadata } from "next";

import { PageHeader } from "@/components/data/page-header";
import { Pagination } from "@/components/data/pagination";
import { EmptyState, ErrorState } from "@/components/data/states";
import { CsvDropzone } from "@/components/discovery/csv-dropzone";
import { ImportTable } from "@/components/discovery/import-table";
import { resolveOrgViewer } from "@/components/layout/org-gate";
import { Card } from "@/components/ui/card";
import { orgRequest } from "@/lib/viewer";

export const metadata: Metadata = { title: "Imports" };

const PAGE_SIZE = 25;

export default async function ImportsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const gate = await resolveOrgViewer();
  if (!gate.ok) return gate.fallback;
  const params = await searchParams;
  const offset = Math.max(0, Math.min(10_000, Number.parseInt(String(params.offset ?? "0"), 10) || 0));
  const result = await orgRequest<ImportBatchPage>(gate.viewer, "/api/v1/imports", {
    query: { limit: PAGE_SIZE, offset },
  });

  return (
    <div className="space-y-6">
      <PageHeader title="Imports" description="Every CSV uploaded to this organization, with what happened to it." />
      <CsvDropzone />
      {!result.ok ? (
        <ErrorState title="Could not load import history" error={result.error} />
      ) : result.data.items.length === 0 ? (
        <EmptyState icon={History} title="No imports yet" description="Upload a CSV above to get started." />
      ) : (
        <Card className="overflow-hidden">
          <ImportTable imports={result.data.items} />
          <Pagination
            total={result.data.total}
            limit={result.data.limit}
            offset={result.data.offset}
            basePath="/discovery/imports"
            params={{}}
          />
        </Card>
      )}
    </div>
  );
}
