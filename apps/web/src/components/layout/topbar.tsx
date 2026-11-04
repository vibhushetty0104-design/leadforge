import { Suspense } from "react";

import { OrganizationSwitcher, UserMenu } from "@/components/layout/account-controls";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { LogoMark } from "@/components/layout/logo";
import { MobileNav } from "@/components/layout/mobile-nav";
import { Skeleton } from "@/components/ui/skeleton";
import { getViewer } from "@/lib/viewer";

async function AccountArea() {
  const viewer = await getViewer();
  if (viewer.kind !== "ready") return null;
  return (
    <>
      <OrganizationSwitcher
        memberships={viewer.me.memberships}
        activeId={viewer.membership?.organization.id ?? null}
      />
      <UserMenu email={viewer.me.profile.email} role={viewer.membership?.role ?? null} />
    </>
  );
}

export function Topbar() {
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-background/75 px-4 backdrop-blur-md sm:px-6">
      <MobileNav />
      <LogoMark className="size-6 md:hidden" />
      <div className="min-w-0 flex-1">
        <Suspense fallback={null}>
          <Breadcrumbs />
        </Suspense>
      </div>
      <div className="flex items-center gap-2">
        <Suspense
          fallback={
            <>
              <Skeleton className="hidden h-9 w-40 sm:block" />
              <Skeleton className="size-9 rounded-full" />
            </>
          }
        >
          <AccountArea />
        </Suspense>
      </div>
    </header>
  );
}
