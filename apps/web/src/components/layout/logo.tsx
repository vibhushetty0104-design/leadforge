import Link from "next/link";
import { useId } from "react";

import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  // Unique per instance: a gradient defined inside a display:none copy (e.g. the
  // desktop sidebar on mobile) would otherwise not paint for the visible one.
  const gradientId = `lf-mark-${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-7 shrink-0", className)}>
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="oklch(0.66 0.19 290)" />
          <stop offset="0.55" stopColor="oklch(0.62 0.16 255)" />
          <stop offset="1" stopColor="oklch(0.72 0.12 180)" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill={`url(#${gradientId})`} />
      <path
        d="M10 8.5v15h12"
        fill="none"
        stroke="white"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M15.5 13.5h7M15.5 18.5h4.5" stroke="white" strokeOpacity=".75" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

export function Logo() {
  return (
    <Link href="/dashboard" className="flex items-center gap-2.5 rounded-md" aria-label="LEADFORGE home">
      <LogoMark />
      <span className="text-[0.95rem] font-semibold tracking-[0.08em]">LEADFORGE</span>
    </Link>
  );
}
