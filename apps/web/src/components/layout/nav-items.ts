import {
  Building2,
  LayoutDashboard,
  type LucideIcon,
  Radar,
  ScanSearch,
  Send,
  Settings,
  UsersRound,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Shown as a small tag for sections whose core features land in a later phase. */
  phase?: string;
};

export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/discovery", label: "Discovery", icon: Radar },
  { href: "/leads", label: "Leads", icon: Building2 },
  { href: "/audits", label: "Audits", icon: ScanSearch, phase: "Phase 3" },
  { href: "/campaigns", label: "Campaigns", icon: Send, phase: "Phase 4" },
  { href: "/crm", label: "CRM", icon: UsersRound, phase: "Phase 4" },
  { href: "/settings", label: "Settings", icon: Settings },
];

export const SEGMENT_LABELS: Record<string, string> = {
  ...Object.fromEntries(NAV_ITEMS.map((item) => [item.href.slice(1), item.label])),
  imports: "Imports",
};
