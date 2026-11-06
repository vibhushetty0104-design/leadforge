import type { DiscoverySummary } from "@leadforge/shared";
import { Activity, AtSign, FileSearch, Globe, History, Plus, ShieldAlert } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { MetricCard } from "@/components/data/metric-card";
import { PageHeader } from "@/components/data/page-header";
import { EmptyState, ErrorState, SeedDataBanner } from "@/components/data/states";
import { CsvDropzone } from "@/components/discovery/csv-dropzone";
import { ImportTable } from "@/components/discovery/import-table";
import { resolveOrgViewer } from "@/components/layout/org-gate";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatNumber } from "@/lib/format";
import { orgRequest } from "@/lib/viewer";

export const metadata: Metadata = { title: "Discovery" };

export default async function DiscoveryPage() {
  const gate = await resolveOrgViewer();
  if (!gate.ok) return gate.fallback;
  const { viewer } = gate;

  const result = await orgRequest<DiscoverySummary>(viewer, "/api/v1/discovery/summary");
  const seeded = viewer.membership.organization.is_development_seed;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Discovery"
        description="Import prospects, check their websites and collect public business information."
        actions={
          <Button asChild variant="secondary">
            <Link href="/leads?new=1">
              <Plus /> Add business
            </Link>
          </Button>
        }
      />
      {seeded ? <SeedDataBanner /> : null}

      {!result.ok ? (
        <ErrorState title="Could not load discovery metrics" error={result.error} />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="With a website"
            icon={Globe}
            value={formatNumber(result.data.with_website)}
            hint={`of ${formatNumber(result.data.total_businesses)} businesses`}
          />
          <MetricCard
            label="Websites inspected"
            icon={FileSearch}
            accent="teal"
            value={formatNumber(result.data.inspected)}
            hint={`${formatNumber(result.data.by_website_status.reachable ?? 0)} reachable`}
          />
          <MetricCard
            label="With an email"
            icon={AtSign}
            accent="blue"
            value={formatNumber(result.data.with_email)}
            hint="On the business record"
          />
          <MetricCard
            label="Background jobs"
            icon={result.data.failed_jobs ? ShieldAlert : Activity}
            accent="amber"
            value={formatNumber(result.data.active_jobs)}
            hint={`active · ${formatNumber(result.data.failed_jobs)} failed`}
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Import a CSV</CardTitle>
            <CardDescription>Columns are matched for you and every row is checked before anything is saved.</CardDescription>
          </CardHeader>
          <CardContent>
            <CsvDropzone />
          </CardContent>
        </Card>

        <Card className="overflow-hidden lg:col-span-3">
          <CardHeader className="flex-row items-center justify-between">
            <div className="space-y-1">
              <CardTitle>Recent imports</CardTitle>
              <CardDescription>The latest files uploaded to this organization.</CardDescription>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link href="/discovery/imports">View all</Link>
            </Button>
          </CardHeader>
          <CardContent className="px-0 pb-1 pt-3">
            {result.ok && result.data.recent_imports.length > 0 ? (
              <ImportTable imports={result.data.recent_imports} />
            ) : (
              <EmptyState
                className="mx-5 mb-4"
                icon={History}
                title="No imports yet"
                description="Your upload history will appear here."
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
