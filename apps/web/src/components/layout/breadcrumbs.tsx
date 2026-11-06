"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { SEGMENT_LABELS } from "@/components/layout/nav-items";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function labelFor(segment: string, parent: string | undefined): string {
  if (UUID.test(segment)) {
    if (parent === "leads") return "Business";
    return parent === "imports" ? "Import" : "Details";
  }
  return SEGMENT_LABELS[segment] ?? segment;
}

export function Breadcrumbs() {
  const segments = usePathname().split("/").filter(Boolean);
  if (segments.length === 0) return null;

  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1.5 text-sm">
        {segments.map((segment, index) => {
          const href = `/${segments.slice(0, index + 1).join("/")}`;
          const last = index === segments.length - 1;
          const label = labelFor(segment, segments[index - 1]);
          return (
            <li key={href} className="flex min-w-0 items-center gap-1.5">
              {index > 0 ? <ChevronRight aria-hidden className="size-3.5 text-subtle-foreground" /> : null}
              {last ? (
                <span aria-current="page" className="truncate font-medium text-foreground">
                  {label}
                </span>
              ) : (
                <Link href={href} className="truncate text-muted-foreground hover:text-foreground">
                  {label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
