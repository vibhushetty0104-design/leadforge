import { DataTableSkeleton } from "@/components/data/data-table";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function LeadsLoading() {
  return (
    <div className="space-y-6" aria-busy aria-label="Loading leads">
      <div className="flex items-end justify-between gap-4">
        <div className="space-y-2">
          <Skeleton className="h-7 w-28" />
          <Skeleton className="h-4 w-80 max-w-full" />
        </div>
        <Skeleton className="h-9 w-36" />
      </div>
      <Skeleton className="h-9 w-full" />
      <Card className="overflow-hidden">
        <DataTableSkeleton />
      </Card>
    </div>
  );
}
