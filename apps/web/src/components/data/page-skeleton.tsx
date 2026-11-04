import { MetricCardSkeleton } from "@/components/data/metric-card";
import { Skeleton } from "@/components/ui/skeleton";

/** Generic page placeholder used by per-segment loading.tsx files. */
export function PageSkeleton() {
  return (
    <div className="space-y-6" aria-busy aria-label="Loading">
      <div className="space-y-2">
        <Skeleton className="h-7 w-40" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <MetricCardSkeleton />
        <MetricCardSkeleton />
        <MetricCardSkeleton />
      </div>
      <Skeleton className="h-64 w-full rounded-xl" />
    </div>
  );
}
