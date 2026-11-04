"use client";

import { Menu } from "lucide-react";
import { Suspense, useState } from "react";

import { Logo } from "@/components/layout/logo";
import { NavLinks, NavList } from "@/components/layout/nav-links";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

export function MobileNav() {
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open navigation">
          <Menu />
        </Button>
      </SheetTrigger>
      <SheetContent aria-describedby={undefined}>
        <SheetTitle className="sr-only">Navigation</SheetTitle>
        <div className="px-5 pt-5">
          <Logo />
        </div>
        <div className="mt-8 px-3">
          <Suspense fallback={<NavList onNavigate={() => setOpen(false)} />}>
            <NavLinks onNavigate={() => setOpen(false)} />
          </Suspense>
        </div>
      </SheetContent>
    </Sheet>
  );
}
