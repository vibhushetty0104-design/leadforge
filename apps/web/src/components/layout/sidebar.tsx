import { Suspense } from "react";

import { Logo } from "@/components/layout/logo";
import { NavLinks, NavList } from "@/components/layout/nav-links";

export function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-border bg-surface/50 px-3 py-5 md:flex">
      <div className="px-2">
        <Logo />
      </div>
      <div className="mt-8 flex-1">
        <Suspense fallback={<NavList />}>
          <NavLinks />
        </Suspense>
      </div>
      <p className="px-3 text-xs text-subtle-foreground">v0.1 · Phase 1 foundation</p>
    </aside>
  );
}
