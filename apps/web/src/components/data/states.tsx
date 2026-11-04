import { AlertTriangle, FlaskConical, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";
import type { ApiFailure } from "@/lib/api/client";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border px-6 py-14 text-center",
        className,
      )}
    >
      <span className="rounded-full bg-muted p-3 ring-1 ring-border">
        <Icon aria-hidden className="size-5 text-muted-foreground" />
      </span>
      <div className="max-w-md space-y-1">
        <h3 className="text-sm font-semibold">{title}</h3>
        <div className="text-sm text-muted-foreground">{description}</div>
      </div>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ error, title = "Something went wrong" }: { error: ApiFailure; title?: string }) {
  return (
    <Card role="alert" className="border-danger/30 bg-danger/5 p-5">
      <div className="flex gap-3">
        <AlertTriangle aria-hidden className="mt-0.5 size-5 shrink-0 text-danger" />
        <div className="min-w-0 space-y-1">
          <h3 className="text-sm font-semibold">{title}</h3>
          <p className="text-sm text-muted-foreground">{error.message}</p>
          <p className="font-mono text-xs text-subtle-foreground">
            {error.code}
            {error.status ? ` · HTTP ${error.status}` : ""}
            {error.requestId ? ` · request ${error.requestId}` : ""}
          </p>
        </div>
      </div>
    </Card>
  );
}

/** Shown whenever the active organization holds fictional development seed data. */
export function SeedDataBanner() {
  return (
    <div
      role="note"
      className="flex items-start gap-3 rounded-lg border border-warning/30 bg-warning/8 px-4 py-3 text-sm"
    >
      <FlaskConical aria-hidden className="mt-0.5 size-4 shrink-0 text-warning" />
      <p className="text-muted-foreground">
        <span className="font-medium text-warning">Development seed data.</span> Every record in this
        organization is fictional and exists only for local development. Switch organizations to work
        with real prospects.
      </p>
    </div>
  );
}
