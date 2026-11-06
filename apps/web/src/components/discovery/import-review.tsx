"use client";

import type { DuplicateAction, ImportDetail, ImportRowRead } from "@leadforge/shared";
import { AlertTriangle, ArrowLeft, CheckCircle2, CopyCheck, Loader2, Trash2, XCircle } from "lucide-react";
import { useEffect, useState, useTransition } from "react";

import {
  cancelImportAction,
  confirmImportAction,
  listImportRowsAction,
  resolveImportRowAction,
} from "@/app/actions";
import { MetricCard } from "@/components/data/metric-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FieldError, Label, NativeSelect } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

type DuplicateInfo = {
  kind: "definite" | "possible";
  reason: string;
  name: string;
  domain: string | null;
  business_id: string | null;
  row_number: number | null;
};

const POLICIES: { value: DuplicateAction; label: string; description: string; adminOnly?: boolean }[] = [
  { value: "skip", label: "Skip them", description: "Keep existing records as they are." },
  {
    value: "update",
    label: "Fill in blanks",
    description: "Add missing details to existing records. Nothing is overwritten.",
    adminOnly: true,
  },
  { value: "create", label: "Import separately", description: "Create new records alongside the existing ones." },
];

function rowName(row: ImportRowRead): string {
  const normalized = row.normalized as { name?: string } | null;
  return normalized?.name || "Unnamed row";
}

function DuplicateRow({
  row,
  importId,
  canUpdate,
  onError,
}: {
  row: ImportRowRead;
  importId: string;
  canUpdate: boolean;
  onError: (message: string) => void;
}) {
  const [resolution, setResolution] = useState<DuplicateAction | null>(row.resolution);
  const [pending, startTransition] = useTransition();
  const match = row.duplicate as DuplicateInfo;
  const inFile = match.row_number !== null;

  function choose(value: string) {
    const next = (value || null) as DuplicateAction | null;
    const previous = resolution;
    setResolution(next);
    startTransition(async () => {
      const result = await resolveImportRowAction(importId, row.id, next);
      if (!result.ok) {
        setResolution(previous);
        onError(result.message);
      }
    });
  }

  return (
    <li className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 space-y-1">
        <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
          <span className="truncate">{rowName(row)}</span>
          <Badge tone={match.kind === "definite" ? "red" : "amber"}>
            {match.kind === "definite" ? "Duplicate" : "Possible duplicate"}
          </Badge>
        </p>
        <p className="text-xs text-subtle-foreground">
          Row {row.row_number}. {match.reason}:{" "}
          {inFile ? `row ${match.row_number} of this file` : match.name}
          {match.domain ? ` (${match.domain})` : ""}
        </p>
      </div>
      <NativeSelect
        aria-label={`Decision for ${rowName(row)}`}
        className="sm:w-56"
        value={resolution ?? ""}
        disabled={pending}
        onChange={(event) => choose(event.target.value)}
      >
        <option value="">{match.kind === "definite" ? "Use the default" : "Leave out for now"}</option>
        <option value="skip">Skip this row</option>
        {canUpdate && !inFile ? <option value="update">Fill in blanks</option> : null}
        <option value="create">Import as separate</option>
      </NativeSelect>
    </li>
  );
}

export function ImportReview({
  batch,
  canUpdate,
  onChange,
  onEditMapping,
}: {
  batch: ImportDetail;
  canUpdate: boolean;
  onChange: (next: ImportDetail) => void;
  onEditMapping: () => void;
}) {
  const preview = batch.preview;
  const [policy, setPolicy] = useState<DuplicateAction>("skip");
  const [validateWebsites, setValidateWebsites] = useState(true);
  const [duplicates, setDuplicates] = useState<ImportRowRead[]>([]);
  const [invalid, setInvalid] = useState<ImportRowRead[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    let current = true;
    void Promise.all([
      listImportRowsAction(batch.id, { duplicatesOnly: true }),
      listImportRowsAction(batch.id, { outcome: "invalid" }),
    ]).then(([duplicateRows, invalidRows]) => {
      if (!current) return;
      if (duplicateRows.ok) setDuplicates(duplicateRows.data.items);
      else setError(duplicateRows.message);
      if (invalidRows.ok) setInvalid(invalidRows.data.items);
      else setError(invalidRows.message);
    });
    return () => {
      current = false;
    };
  }, [batch.id]);

  if (!preview) return null;
  const duplicateTotal = preview.definite_duplicates + preview.possible_duplicates;
  const canImport = preview.valid > 0;

  function confirm() {
    setError(null);
    startTransition(async () => {
      const result = await confirmImportAction(batch.id, { duplicatePolicy: policy, validateWebsites });
      if (result.ok) onChange(result.data);
      else setError(result.message);
    });
  }

  function discard() {
    startTransition(async () => {
      const result = await cancelImportAction(batch.id);
      if (result.ok) onChange(result.data);
      else setError(result.message);
    });
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <MetricCard label="Valid rows" icon={CheckCircle2} accent="teal" value={preview.valid.toLocaleString("en")} hint={`of ${preview.total.toLocaleString("en")} rows`} />
        <MetricCard label="Rejected" icon={XCircle} accent="amber" value={preview.invalid.toLocaleString("en")} hint={`${preview.with_warnings.toLocaleString("en")} more with warnings`} />
        <MetricCard label="Duplicates found" icon={CopyCheck} accent="blue" value={duplicateTotal.toLocaleString("en")} hint={`${preview.possible_duplicates.toLocaleString("en")} to review`} />
      </div>

      {duplicates.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Review duplicates</CardTitle>
            <CardDescription>
              A shared website does not prove two businesses are the same. Possible duplicates are left out unless you
              decide otherwise.
              {duplicateTotal > duplicates.length ? ` Showing the first ${duplicates.length}.` : ""}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-2">
            <ul className="divide-y divide-border/70">
              {duplicates.map((row) => (
                <DuplicateRow key={row.id} row={row} importId={batch.id} canUpdate={canUpdate} onError={setError} />
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {invalid.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Rows that will be rejected</CardTitle>
            <CardDescription>
              Fix these in your file and import them again.
              {preview.invalid > invalid.length ? ` Showing the first ${invalid.length}.` : ""}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-2">
            <ul className="divide-y divide-border/70">
              {invalid.map((row) => (
                <li key={row.id} className="flex gap-2.5 py-2.5 text-sm">
                  <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-warning" />
                  <div className="min-w-0">
                    <p className="font-medium">
                      Row {row.row_number}: {rowName(row)}
                    </p>
                    <p className="text-muted-foreground">{row.errors.join(" ")}</p>
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Confirm import</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 pt-3">
          {preview.definite_duplicates > 0 ? (
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Default for confirmed duplicates</legend>
              <div className="grid gap-2 sm:grid-cols-3">
                {POLICIES.filter((option) => canUpdate || !option.adminOnly).map((option) => (
                  <label
                    key={option.value}
                    className="flex cursor-pointer gap-2.5 rounded-lg border border-border p-3 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary/8"
                  >
                    <input
                      type="radio"
                      name="duplicate-policy"
                      value={option.value}
                      checked={policy === option.value}
                      onChange={() => setPolicy(option.value)}
                      className="mt-0.5 accent-[var(--color-primary)]"
                    />
                    <span>
                      <span className="block font-medium">{option.label}</span>
                      <span className="block text-xs text-muted-foreground">{option.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          ) : null}
          <div className="flex items-start gap-2.5">
            <input
              id="validate-websites"
              type="checkbox"
              checked={validateWebsites}
              onChange={(event) => setValidateWebsites(event.target.checked)}
              className="mt-0.5 accent-[var(--color-primary)]"
            />
            <div>
              <Label htmlFor="validate-websites">Check websites after importing</Label>
              <p className="text-xs text-muted-foreground">
                Runs in the background and records whether each website responds.
              </p>
            </div>
          </div>
          <FieldError message={error ?? undefined} />
          <div className="flex flex-wrap justify-between gap-2">
            <div className="flex gap-2">
              <Button type="button" variant="ghost" onClick={onEditMapping} disabled={pending}>
                <ArrowLeft /> Change columns
              </Button>
              <Button type="button" variant="ghost" onClick={discard} disabled={pending}>
                <Trash2 /> Discard
              </Button>
            </div>
            <Button type="button" onClick={confirm} disabled={pending || !canImport}>
              {pending ? <Loader2 className="animate-spin" /> : null}
              Start import
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
