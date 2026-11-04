"use client";

import type { MembershipRead } from "@leadforge/shared";
import { Building, ChevronsUpDown, LogOut, Settings } from "lucide-react";
import Link from "next/link";
import { useTransition } from "react";
import { toast } from "sonner";

import { signOutAction, switchOrganizationAction } from "@/app/actions";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { humanize } from "@/lib/format";

export function OrganizationSwitcher({
  memberships,
  activeId,
}: {
  memberships: MembershipRead[];
  activeId: string | null;
}) {
  const [pending, startTransition] = useTransition();
  const active = memberships.find((m) => m.organization.id === activeId);
  if (!active) return null;

  function select(id: string) {
    if (id === activeId) return;
    startTransition(async () => {
      const result = await switchOrganizationAction(id);
      if (result.ok) toast.success("Organization switched");
      else toast.error(result.message);
    });
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={pending}
        className="flex h-9 max-w-56 items-center gap-2 rounded-md border border-border bg-surface px-2.5 text-sm transition-colors hover:border-border-strong disabled:opacity-60"
      >
        <Building className="size-4 shrink-0 text-subtle-foreground" />
        <span className="truncate">{active.organization.name}</span>
        <ChevronsUpDown className="size-3.5 shrink-0 text-subtle-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>Organizations</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={activeId ?? undefined} onValueChange={select}>
          {memberships.map((m) => (
            <DropdownMenuRadioItem key={m.organization.id} value={m.organization.id}>
              <span className="flex-1 truncate">{m.organization.name}</span>
              {m.organization.is_development_seed ? <Badge tone="amber">Seed</Badge> : null}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function UserMenu({ email, role }: { email: string | null; role: string | null }) {
  const [pending, startTransition] = useTransition();
  const initial = (email?.[0] ?? "?").toUpperCase();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Account menu"
        className="flex size-9 items-center justify-center rounded-full bg-gradient-to-br from-primary to-info text-sm font-semibold text-white ring-1 ring-white/10 transition-opacity hover:opacity-90"
      >
        {initial}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel className="flex flex-col gap-0.5">
          <span className="truncate text-sm text-foreground">{email ?? "Signed in"}</span>
          {role ? <span>{humanize(role)}</span> : null}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings">
            <Settings /> Settings
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem
          disabled={pending}
          onSelect={() => startTransition(() => signOutAction())}
        >
          <LogOut /> {pending ? "Signing out…" : "Sign out"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
