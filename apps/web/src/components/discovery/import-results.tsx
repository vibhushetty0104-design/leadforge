"use client";

import type { ImportDetail, ImportRowOutcome, ImportRowRead } from "@leadforge/shared";
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, CopyCheck, RefreshCw, XCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { listImportRowsAction } from "@/app/actions";
import { DataTableSkeleton } from "@/components/data/data-table";
import { MetricCard } from "@/components/data/metric-card";
import { RowOutcomeBadge } from "@/components/data/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FieldError } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

const FILTERS: { label: string; outcome?: ImportRowOutcome }[] = [
  { label: "All rows" },
  { label: "Created", outcome: "created" },
  { label: "Updated", outcome: "updated" },
  { label: "Skipped", outcome: "skipped_duplicate" },
  { label: "Not imported", outcome: "needs_review" },
  { label: "Rejected", outcome: "invalid" },
];
const PAGE_SIZE = 25;

function count(value: number, noun: string): string {
  return `${value.toLocaleString("en")} ${noun}${value === 1 ? "" : "s"}`;
}

function rowLabel(row: ImportRowRead): string {
  return (row.normalized as { name?: string } | null)?.name || "Unnamed row";
}

export function ImportResults({ batch }: { batch: ImportDetail }) {
  const [outcome, setOutcome] = useState<ImportRowOutcome | undefined>();
  const [offset, setOffset] = useState(0);
  const [rows, setRows] = useState<ImportRowRead[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    void listImportRowsAction(batch.id, { outcome, offset }).then((result) => {
      if (!current) return;
      if (result.ok) {
        setRows(result.data.items);
        setTotal(result.data.total);
      } else {
        setError(result.message);
      }
    });
    return () => {
      current = false;
    };
  }, [batch.id, outcome, offset]);

  const failed = batch.status === "failed";
  const problems = batch.invalid_count + batch.review_count;

  return (
    <div className="space-y-4">
      {failed ? (
        <div role="alert" className="flex gap-3 rounded-lg border border-danger/30 bg-danger/5 px-4 py-3 text-sm">
          <XCircle aria-hidden className="mt-0.5 size-4 shrink-0 text-danger" />
          <p>
            <span className="font-medium">This import did not finish.</span>{" "}
            <span className="text-muted-foreground">{batch.error_message}</span>
          </p>
        </div>
      ) : problems > 0 || batch.warning_count > 0 ? (
        <div role="status" className="flex gap-3 rounded-lg border border-warning/30 bg-warning/8 px-4 py-3 text-sm">
          <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-warning" />
          <p className="text-muted-foreground">
            Finished with {count(problems, "row")} not imported and {count(batch.warning_count, "warning")}. Filter
            the rows below to see why.
          </p>
        </div>
      ) : (
        <div role="status" className="flex gap-3 rounded-lg border border-success/30 bg-success/8 px-4 py-3 text-sm">
          <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0 text-success" />
          <p className="text-muted-foreground">Every row was processed successfully.</p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Created" icon={CheckCircle2} accent="teal" value={batch.created_count.toLocaleString("en")} />
        <MetricCard label="Updated" icon={RefreshCw} accent="blue" value={batch.updated_count.toLocaleString("en")} />
        <MetricCard label="Skipped duplicates" icon={CopyCheck} accent="violet" value={batch.skipped_count.toLocaleString("en")} />
        <MetricCard label="Rejected or held back" icon={XCircle} accent="amber" value={problems.toLocaleString("en")} />
      </div>

      {batch.created_count > 0 ? (
        <Button asChild variant="secondary">
          <Link href={`/leads?import_id=${batch.id}`}>View imported businesses</Link>
        </Button>
      ) : null}

      <Card className="overflow-hidden">
        <CardHeader>
          <CardTitle>Row results</CardTitle>
          <div role="group" aria-label="Filter rows" className="mt-2 flex flex-wrap gap-1.5">
            {FILTERS.map((filter) => (
              <button
                key={filter.label}
                type="button"
                aria-pressed={outcome === filter.outcome}
                onClick={() => {
                  setOutcome(filter.outcome);
                  setOffset(0);
                }}
                className={cn(
                  "rounded-full border px-2.5 py-1 text-xs transition-colors",
                  outcome === filter.outcome
                    ? "border-primary bg-primary/12 text-foreground"
                    : "border-border text-muted-foreground hover:text-foreground",
                )}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent className="px-0 pb-1">
          <FieldError message={error ?? undefined} />
          {rows === null ? (
            error ? null : <DataTableSkeleton rows={4} columns={3} />
          ) : rows.length === 0 ? (
            <p className="px-5 pb-4 text-sm text-muted-foreground">No rows match this filter.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-16">Row</TableHead>
                  <TableHead>Business</TableHead>
                  <TableHead>Result</TableHead>
                  <TableHead>Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => {
                  const reason = (row.duplicate as { reason?: string } | null)?.reason;
                  const notes = [...row.errors, ...row.warnings];
                  if (reason && row.outcome !== "created") notes.unshift(reason);
                  return (
                    <TableRow key={row.id}>
                      <TableCell className="text-muted-foreground tabular-nums">{row.row_number}</TableCell>
                      <TableCell className="font-medium">
                        {row.business_id ? (
                          <Link href={`/leads/${row.business_id}`} className="hover:text-primary-hover">
                            {rowLabel(row)}
                          </Link>
                        ) : (
                          rowLabel(row)
                        )}
                      </TableCell>
                      <TableCell>
                        <RowOutcomeBadge outcome={row.outcome} />
                      </TableCell>
                      <TableCell className="min-w-56 text-muted-foreground">{notes.join(" ") || "—"}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
          {total > PAGE_SIZE ? (
            <div className="flex items-center justify-between border-t border-border px-4 py-3 text-sm">
              <p className="text-muted-foreground tabular-nums">
                {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total.toLocaleString("en")}
              </p>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                  <ChevronLeft /> Previous
                </Button>
                <Button variant="secondary" size="sm" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                  Next <ChevronRight />
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
