"use client";

import type { ImportDetail } from "@leadforge/shared";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const POLL_MS = 1500;
const MAX_FAILURES = 5;

export function ImportProgress({ batch, onChange }: { batch: ImportDetail; onChange: (next: ImportDetail) => void }) {
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;

    async function poll() {
      try {
        const response = await fetch(`/api/imports/${batch.id}`, { cache: "no-store" });
        if (!response.ok) throw new Error(String(response.status));
        const next = (await response.json()) as ImportDetail;
        if (cancelled) return;
        failures = 0;
        setProblem(null);
        onChange(next);
      } catch {
        failures += 1;
        if (failures >= MAX_FAILURES && !cancelled) {
          setProblem("Progress updates stopped. The import keeps running; refresh to check on it.");
        }
      }
      if (!cancelled) timer = setTimeout(() => void poll(), POLL_MS);
    }

    timer = setTimeout(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [batch.id, onChange]);

  const percent = batch.total_rows ? Math.round((batch.processed_rows / batch.total_rows) * 100) : 0;
  const waiting = batch.status === "queued";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Loader2 aria-hidden className="size-4 animate-spin text-primary-hover" />
          {waiting ? "Waiting for a worker" : "Importing"}
        </CardTitle>
        <CardDescription>
          {waiting
            ? "This import is queued. It starts as soon as a background worker is free."
            : "You can leave this page; the import continues in the background."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <div
          role="progressbar"
          aria-label="Import progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          className="h-2 overflow-hidden rounded-full bg-muted"
        >
          <div
            className="h-full rounded-full bg-gradient-to-r from-primary to-info transition-[width] duration-500"
            style={{ width: `${percent}%` }}
          />
        </div>
        <p className="text-sm text-muted-foreground tabular-nums">
          {batch.processed_rows.toLocaleString("en")} of {batch.total_rows.toLocaleString("en")} rows processed
        </p>
        {problem ? (
          <p role="alert" className="text-sm text-danger">
            {problem}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
