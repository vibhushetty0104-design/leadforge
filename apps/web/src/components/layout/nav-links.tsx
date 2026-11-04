"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { NAV_ITEMS } from "@/components/layout/nav-items";
import { cn } from "@/lib/utils";

export function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return <NavList activePath={pathname} onNavigate={onNavigate} />;
}

/** Pathname-independent rendering, also used as the prerendered fallback. */
export function NavList({
  activePath,
  onNavigate,
}: {
  activePath?: string;
  onNavigate?: () => void;
}) {
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5">
      {NAV_ITEMS.map(({ href, label, icon: Icon, phase }) => {
        const active = activePath === href || activePath?.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
              active
                ? "bg-primary/12 text-foreground shadow-[inset_2px_0_0_0_var(--color-primary)]"
                : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
            )}
          >
            <Icon
              className={cn(
                "size-4 shrink-0",
                active ? "text-primary-hover" : "text-subtle-foreground group-hover:text-muted-foreground",
              )}
            />
            <span className="flex-1">{label}</span>
            {phase ? (
              <span className="rounded border border-border px-1.5 py-px text-[10px] font-medium text-subtle-foreground">
                {phase}
              </span>
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
}
