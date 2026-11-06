"use client";

import type { ImportDetail, ImportField } from "@leadforge/shared";
import { Loader2, Trash2 } from "lucide-react";
import { useState, useTransition } from "react";

import { cancelImportAction, saveImportMappingAction } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FieldError, Label, NativeSelect } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { duplicateColumns, IMPORT_FIELDS } from "@/lib/csv";

type Mapping = Partial<Record<ImportField, string>>;

export function ColumnMapper({ batch, onChange }: { batch: ImportDetail; onChange: (next: ImportDetail) => void }) {
  const [mapping, setMapping] = useState<Mapping>(batch.column_mapping ?? batch.suggested_mapping);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const repeated = duplicateColumns(mapping);
  const nameMissing = !mapping.business_name;

  function select(field: ImportField, header: string) {
    setMapping((current) => {
      const next = { ...current };
      if (header) next[field] = header;
      else delete next[field];
      return next;
    });
  }

  function submit() {
    setError(null);
    startTransition(async () => {
      const result = await saveImportMappingAction(batch.id, mapping);
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
      <Card>
        <CardHeader>
          <CardTitle>Match your columns</CardTitle>
          <CardDescription>
            {batch.total_rows.toLocaleString("en")} rows found in {batch.filename}. Columns with familiar names are
            matched already. Only the business name is required.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {IMPORT_FIELDS.map(({ field, label, hint, required }) => {
            const sample = batch.sample_rows[0]?.[mapping[field] ?? ""];
            return (
              <div key={field} className="flex min-w-0 flex-col gap-1.5">
                <Label htmlFor={`map-${field}`}>
                  {label}
                  {required ? <span className="text-danger"> *</span> : null}
                </Label>
                <NativeSelect
                  id={`map-${field}`}
                  value={mapping[field] ?? ""}
                  onChange={(event) => select(field, event.target.value)}
                >
                  <option value="">Don&apos;t import</option>
                  {batch.headers.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </NativeSelect>
                <p className="truncate text-xs text-subtle-foreground">{sample ? `e.g. ${sample}` : hint}</p>
              </div>
            );
          })}
        </CardContent>
      </Card>

      <Card className="overflow-hidden">
        <CardHeader>
          <CardTitle>File preview</CardTitle>
          <CardDescription>The first {batch.sample_rows.length} rows, exactly as uploaded.</CardDescription>
        </CardHeader>
        <CardContent className="px-0 pb-1">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                {batch.headers.map((header) => (
                  <TableHead key={header}>{header}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {batch.sample_rows.map((row, index) => (
                <TableRow key={index}>
                  {batch.headers.map((header) => (
                    <TableCell key={header} className="max-w-56 truncate text-muted-foreground">
                      {row[header] ?? ""}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {repeated.length ? <FieldError message={`Each column can only be used once: ${repeated.join(", ")}.`} /> : null}
      {nameMissing ? <FieldError message="Choose the column that holds the business name." /> : null}
      <FieldError message={error ?? undefined} />
      <div className="flex flex-wrap justify-between gap-2">
        <Button type="button" variant="ghost" onClick={discard} disabled={pending}>
          <Trash2 /> Discard import
        </Button>
        <Button type="button" onClick={submit} disabled={pending || nameMissing || repeated.length > 0}>
          {pending ? <Loader2 className="animate-spin" /> : null}
          Validate {batch.total_rows.toLocaleString("en")} rows
        </Button>
      </div>
    </div>
  );
}
