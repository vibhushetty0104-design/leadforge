import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Link-based pagination; preserves the current filters in the query string. */
export function Pagination({
  total,
  limit,
  offset,
  basePath,
  params,
}: {
  total: number;
  limit: number;
  offset: number;
  basePath: string;
  params: Record<string, string | undefined>;
}) {
  if (total === 0) return null;
  const start = offset + 1;
  const end = Math.min(offset + limit, total);

  const href = (nextOffset: number) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) if (value) search.set(key, value);
    if (nextOffset > 0) search.set("offset", String(nextOffset));
    const query = search.toString();
    return query ? `${basePath}?${query}` : basePath;
  };

  const linkClass = cn(buttonVariants({ variant: "secondary", size: "sm" }));
  const disabledClass = cn(linkClass, "pointer-events-none opacity-40");

  return (
    <div className="flex items-center justify-between gap-3 border-t border-border px-4 py-3 text-sm">
      <p className="text-muted-foreground tabular-nums">
        {formatNumber(start)}–{formatNumber(end)} of {formatNumber(total)}
      </p>
      <div className="flex gap-2">
        {offset > 0 ? (
          <Link href={href(Math.max(0, offset - limit))} className={linkClass}>
            <ChevronLeft /> Previous
          </Link>
        ) : (
          <span aria-disabled className={disabledClass}>
            <ChevronLeft /> Previous
          </span>
        )}
        {end < total ? (
          <Link href={href(offset + limit)} className={linkClass}>
            Next <ChevronRight />
          </Link>
        ) : (
          <span aria-disabled className={disabledClass}>
            Next <ChevronRight />
          </span>
        )}
      </div>
    </div>
  );
}
