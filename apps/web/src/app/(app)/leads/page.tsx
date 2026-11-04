import { BUSINESS_STATUSES, type BusinessPage, type BusinessRead, type BusinessStatus } from "@leadforge/shared";
import { Building2, ExternalLink, Search, SearchX } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { DataTable, type Column } from "@/components/data/data-table";
import { PageHeader } from "@/components/data/page-header";
import { Pagination } from "@/components/data/pagination";
import { EmptyState, ErrorState, SeedDataBanner } from "@/components/data/states";
import { BusinessStatusBadge } from "@/components/data/status-badge";
import { resolveOrgViewer } from "@/components/layout/org-gate";
import { AddBusinessDialog } from "@/components/leads/add-business-dialog";
import { DeleteBusinessButton } from "@/components/leads/delete-business-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { formatDate, humanize } from "@/lib/format";
import { orgRequest } from "@/lib/viewer";

export const metadata: Metadata = { title: "Leads" };

const PAGE_SIZE = 25;

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function one(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function isStatus(value: string | undefined): value is BusinessStatus {
  return BUSINESS_STATUSES.includes(value as BusinessStatus);
}

export default async function LeadsPage({ searchParams }: { searchParams: SearchParams }) {
  const gate = await resolveOrgViewer();
  if (!gate.ok) return gate.fallback;
  const { viewer } = gate;

  const params = await searchParams;
  const q = one(params.q)?.trim().slice(0, 100) || undefined;
  const statusParam = one(params.status);
  const status = isStatus(statusParam) ? statusParam : undefined;
  const offset = Math.max(0, Math.min(10_000, Number.parseInt(one(params.offset) ?? "0", 10) || 0));
  const openNew = one(params.new) === "1";
  const canDelete = viewer.membership.role === "owner" || viewer.membership.role === "admin";

  const result = await orgRequest<BusinessPage>(viewer, "/api/v1/businesses", {
    query: { limit: PAGE_SIZE, offset, q, status },
  });

  const columns: Column<BusinessRead>[] = [
    {
      id: "name",
      header: "Business",
      cell: (b) => (
        <div className="min-w-0">
          <Link href={`/leads/${b.id}`} className="font-medium hover:text-primary-hover">
            {b.name}
          </Link>
          {b.website_url ? (
            <a
              href={b.website_url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="mt-0.5 flex items-center gap-1 text-xs text-subtle-foreground hover:text-muted-foreground"
            >
              {b.domain} <ExternalLink aria-hidden className="size-3" />
            </a>
          ) : (
            <p className="mt-0.5 text-xs text-subtle-foreground">No website</p>
          )}
        </div>
      ),
    },
    {
      id: "industry",
      header: "Industry",
      hideBelow: "md",
      cell: (b) => <span className="text-muted-foreground">{b.industry ?? "—"}</span>,
    },
    {
      id: "location",
      header: "Location",
      hideBelow: "lg",
      cell: (b) => (
        <span className="text-muted-foreground">
          {[b.city, b.region, b.country_code].filter(Boolean).join(", ") || "—"}
        </span>
      ),
    },
    { id: "status", header: "Status", cell: (b) => <BusinessStatusBadge status={b.status} /> },
    {
      id: "source",
      header: "Source",
      hideBelow: "lg",
      cell: (b) =>
        b.source === "development_seed" ? <Badge tone="amber">Seed</Badge> : <span className="text-muted-foreground">{humanize(b.source)}</span>,
    },
    {
      id: "added",
      header: "Added",
      hideBelow: "sm",
      cell: (b) => <span className="whitespace-nowrap text-muted-foreground">{formatDate(b.created_at)}</span>,
    },
    ...(canDelete
      ? [
          {
            id: "actions",
            header: <span className="sr-only">Actions</span>,
            className: "w-12 text-right",
            cell: (b: BusinessRead) => <DeleteBusinessButton businessId={b.id} businessName={b.name} compact />,
          },
        ]
      : []),
  ];

  const filtered = Boolean(q || status);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Leads"
        description="Businesses you are researching. Add them manually; CSV import arrives with the import worker."
        actions={<AddBusinessDialog defaultOpen={openNew} />}
      />
      {viewer.membership.organization.is_development_seed ? <SeedDataBanner /> : null}

      <form method="get" action="/leads" className="flex flex-col gap-2 sm:flex-row" role="search">
        <div className="relative flex-1">
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle-foreground" />
          <Input name="q" defaultValue={q} placeholder="Search by name or domain" aria-label="Search businesses" className="pl-9" maxLength={100} />
        </div>
        <NativeSelect name="status" defaultValue={status ?? ""} aria-label="Filter by status" className="sm:w-48">
          <option value="">All statuses</option>
          {BUSINESS_STATUSES.map((s) => (
            <option key={s} value={s}>
              {humanize(s)}
            </option>
          ))}
        </NativeSelect>
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
            description="Add the first prospect you want to research. Website audits and lead scoring will build on these records."
          />
        )
      ) : (
        <Card className="overflow-hidden">
          <DataTable caption="Businesses" columns={columns} rows={result.data.items} rowKey={(b) => b.id} />
          <Pagination
            total={result.data.total}
            limit={result.data.limit}
            offset={result.data.offset}
            basePath="/leads"
            params={{ q, status }}
          />
        </Card>
      )}
    </div>
  );
}
