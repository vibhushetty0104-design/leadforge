import {
  BUSINESS_STATUSES,
  RECORD_SOURCES,
  WEBSITE_STATUSES,
  type BusinessExportRequest,
  type BusinessPage,
} from "@leadforge/shared";
import { Building2, Search, SearchX, Upload } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/data/page-header";
import { Pagination } from "@/components/data/pagination";
import { EmptyState, ErrorState, SeedDataBanner } from "@/components/data/states";
import { resolveOrgViewer } from "@/components/layout/org-gate";
import { BusinessDirectory } from "@/components/leads/business-directory";
import { BusinessFormDialog } from "@/components/leads/business-form-dialog";
import { ExportButton } from "@/components/leads/export-button";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { humanize } from "@/lib/format";
import { orgRequest } from "@/lib/viewer";

export const metadata: Metadata = { title: "Leads" };

const PAGE_SIZE = 25;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function one(value: string | string[] | undefined): string | undefined {
  const text = Array.isArray(value) ? value[0] : value;
  return text?.trim() || undefined;
}

function oneOf<T extends string>(value: string | undefined, allowed: readonly T[]): T | undefined {
  return allowed.includes(value as T) ? (value as T) : undefined;
}

export default async function LeadsPage({ searchParams }: { searchParams: SearchParams }) {
  const gate = await resolveOrgViewer();
  if (!gate.ok) return gate.fallback;
  const { viewer } = gate;

  const params = await searchParams;
  const filters = {
    q: one(params.q)?.slice(0, 100),
    status: oneOf(one(params.status), BUSINESS_STATUSES),
    website_status: oneOf(one(params.website_status), WEBSITE_STATUSES),
    source: oneOf(one(params.source), RECORD_SOURCES),
    industry: one(params.industry)?.slice(0, 120),
    country_code: /^[A-Za-z]{2}$/.test(one(params.country_code) ?? "") ? one(params.country_code) : undefined,
    has_email: oneOf(one(params.has_email), ["true", "false"] as const),
    import_id: UUID.test(one(params.import_id) ?? "") ? one(params.import_id) : undefined,
  };
  const offset = Math.max(0, Math.min(10_000, Number.parseInt(one(params.offset) ?? "0", 10) || 0));
  const openNew = one(params.new) === "1";
  const canDelete = viewer.membership.role === "owner" || viewer.membership.role === "admin";

  const result = await orgRequest<BusinessPage>(viewer, "/api/v1/businesses", {
    query: { limit: PAGE_SIZE, offset, ...filters },
  });
  const filtered = Object.values(filters).some(Boolean);
  const exportRequest: BusinessExportRequest = {
    ...filters,
    has_email: filters.has_email ? filters.has_email === "true" : undefined,
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Leads"
        description="Your business directory. Search, filter, inspect websites and export."
        actions={
          <>
            <ExportButton request={exportRequest} />
            <Button asChild variant="secondary">
              <Link href="/discovery/imports">
                <Upload /> Import CSV
              </Link>
            </Button>
            <BusinessFormDialog defaultOpen={openNew} />
          </>
        }
      />
      {viewer.membership.organization.is_development_seed ? <SeedDataBanner /> : null}

      <form method="get" action="/leads" role="search" className="space-y-2">
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle-foreground" />
            <Input name="q" defaultValue={filters.q} placeholder="Search by name or domain" aria-label="Search businesses" className="pl-9" maxLength={100} />
          </div>
          <div className="flex gap-2">
            <Button type="submit" variant="secondary" className="flex-1 sm:flex-none">
              Apply
            </Button>
            {filtered ? (
              <Button asChild variant="ghost">
                <Link href="/leads">Clear</Link>
              </Button>
            ) : null}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-6">
          <NativeSelect name="status" defaultValue={filters.status ?? ""} aria-label="Filter by status">
            <option value="">All statuses</option>
            {BUSINESS_STATUSES.map((s) => (
              <option key={s} value={s}>
                {humanize(s)}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect name="website_status" defaultValue={filters.website_status ?? ""} aria-label="Filter by website status">
            <option value="">Any website</option>
            {WEBSITE_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s === "unknown" ? "Not checked" : humanize(s)}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect name="source" defaultValue={filters.source ?? ""} aria-label="Filter by source">
            <option value="">All sources</option>
            {RECORD_SOURCES.map((s) => (
              <option key={s} value={s}>
                {humanize(s)}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect name="has_email" defaultValue={filters.has_email ?? ""} aria-label="Filter by email">
            <option value="">Email: any</option>
            <option value="true">Has email</option>
            <option value="false">No email</option>
          </NativeSelect>
          <Input name="industry" defaultValue={filters.industry} placeholder="Category" aria-label="Filter by category" maxLength={120} />
          <Input name="country_code" defaultValue={filters.country_code} placeholder="Country code" aria-label="Filter by country code" maxLength={2} />
        </div>
        {filters.import_id ? <input type="hidden" name="import_id" value={filters.import_id} /> : null}
      </form>

      {!result.ok ? (
        <ErrorState title="Could not load businesses" error={result.error} />
      ) : result.data.items.length === 0 ? (
        filtered ? (
          <EmptyState icon={SearchX} title="No matches" description="No businesses match these filters." />
        ) : (
          <EmptyState
            icon={Building2}
            title="No businesses yet"
            description="Add a prospect above, or import a CSV to bring in many at once."
          />
        )
      ) : (
        <Card className="overflow-hidden">
          <BusinessDirectory key={offset} items={result.data.items} canDelete={canDelete} />
          <Pagination
            total={result.data.total}
            limit={result.data.limit}
            offset={result.data.offset}
            basePath="/leads"
            params={filters}
          />
        </Card>
      )}
    </div>
  );
}
