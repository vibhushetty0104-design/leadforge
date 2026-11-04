import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Accent = "violet" | "blue" | "teal" | "amber";

const ACCENTS: Record<Accent, string> = {
  violet: "text-primary-hover bg-primary/10 ring-primary/20",
  blue: "text-info bg-info/10 ring-info/20",
  teal: "text-success bg-success/10 ring-success/20",
  amber: "text-warning bg-warning/10 ring-warning/20",
};

export function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
  accent = "violet",
}: {
  label: string;
  /** Pre-formatted value; pass "—" when there is no data yet rather than a fake zero. */
  value: ReactNode;
  hint?: ReactNode;
  icon: LucideIcon;
  accent?: Accent;
}) {
  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">{label}</p>
        <span className={cn("rounded-md p-1.5 ring-1", ACCENTS[accent])}>
          <Icon aria-hidden className="size-4" />
        </span>
      </div>
      <div>
        <p className="text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
        {hint ? <p className="mt-1 text-xs text-subtle-foreground">{hint}</p> : null}
      </div>
    </Card>
  );
}

export function MetricCardSkeleton() {
  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="size-7" />
      </div>
      <div className="space-y-2">
        <Skeleton className="h-7 w-16" />
        <Skeleton className="h-3 w-28" />
      </div>
    </Card>
  );
}
