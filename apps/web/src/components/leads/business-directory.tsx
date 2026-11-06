"use client";

import type { BusinessRead } from "@leadforge/shared";
import { ExternalLink, Loader2, ScanSearch, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { bulkInspectAction } from "@/app/actions";
import { DataTable, type Column } from "@/components/data/data-table";
import { BusinessStatusBadge, WebsiteStatusBadge } from "@/components/data/status-badge";
import { DeleteBusinessButton } from "@/components/leads/delete-business-button";
import { ExportButton } from "@/components/leads/export-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate, humanize } from "@/lib/format";

export function BusinessDirectory({ items, canDelete }: { items: BusinessRead[]; canDelete: boolean }) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const allSelected = items.length > 0 && items.every((business) => selected.has(business.id));

  function toggle(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function inspectSelected() {
    startTransition(async () => {
      const result = await bulkInspectAction([...selected]);
      if (!result.ok) {
        toast.error(result.message);
        return;
      }
      const { queued, already_active: active, skipped_no_website: skipped } = result.data;
      toast.success(`${queued} inspection${queued === 1 ? "" : "s"} queued`, {
        description:
          [active ? `${active} already running` : "", skipped ? `${skipped} without a website` : ""]
            .filter(Boolean)
            .join(" · ") || undefined,
      });
      setSelected(new Set());
      router.refresh();
    });
  }

  const columns: Column<BusinessRead>[] = [
    {
      id: "select",
      header: (
        <input
          type="checkbox"
          aria-label="Select all businesses on this page"
          checked={allSelected}
          onChange={() => setSelected(allSelected ? new Set() : new Set(items.map((business) => business.id)))}
          className="accent-[var(--color-primary)]"
        />
      ),
      className: "w-10",
      cell: (business) => (
        <input
          type="checkbox"
          aria-label={`Select ${business.name}`}
          checked={selected.has(business.id)}
          onChange={() => toggle(business.id)}
          className="accent-[var(--color-primary)]"
        />
      ),
    },
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
      id: "category",
      header: "Category",
      hideBelow: "lg",
      cell: (b) => <span className="text-muted-foreground">{b.industry ?? "—"}</span>,
    },
    {
      id: "location",
      header: "Location",
      hideBelow: "lg",
      cell: (b) => (
        <span className="text-muted-foreground">{[b.city, b.region, b.country_code].filter(Boolean).join(", ") || "—"}</span>
      ),
    },
    { id: "status", header: "Status", cell: (b) => <BusinessStatusBadge status={b.status} /> },
    {
      id: "website",
      header: "Website",
      hideBelow: "md",
      cell: (b) => (b.website_url ? <WebsiteStatusBadge status={b.website_status} /> : <span className="text-subtle-foreground">—</span>),
    },
    {
      id: "source",
      header: "Source",
      hideBelow: "lg",
      cell: (b) =>
        b.source === "development_seed" ? (
          <Badge tone="amber">Seed</Badge>
        ) : (
          <span className="text-muted-foreground">{humanize(b.source)}</span>
        ),
    },
    {
      id: "added",
      header: "Added",
      hideBelow: "lg",
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

  return (
    <>
      {selected.size > 0 ? (
        <div
          role="toolbar"
          aria-label="Bulk actions"
          className="flex flex-wrap items-center gap-2 border-b border-border bg-primary/8 px-4 py-2.5"
        >
          <p className="mr-auto text-sm font-medium tabular-nums">{selected.size} selected</p>
          <Button type="button" size="sm" onClick={inspectSelected} disabled={pending}>
            {pending ? <Loader2 className="animate-spin" /> : <ScanSearch />}
            Inspect websites
          </Button>
          <ExportButton request={{ business_ids: [...selected] }} label="Export selected" />
          <Button type="button" variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
            <X /> Clear
          </Button>
        </div>
      ) : null}
      <DataTable caption="Businesses" columns={columns} rows={items} rowKey={(b) => b.id} />
    </>
  );
}
