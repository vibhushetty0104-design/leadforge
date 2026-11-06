"use client";

import type { BusinessInspection } from "@leadforge/shared";
import { ExternalLink, Loader2, Mail, Phone, ScanSearch, Share2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition, type ReactNode } from "react";
import { toast } from "sonner";

import { inspectBusinessAction } from "@/app/actions";
import { InspectionStatusBadge } from "@/components/data/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime, humanize } from "@/lib/format";

const POLL_MS = 2000;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <h3 className="text-xs font-medium tracking-wide text-subtle-foreground uppercase">{title}</h3>
      {children}
    </div>
  );
}

export function InspectionPanel({
  businessId,
  initial,
  hasWebsite,
}: {
  businessId: string;
  initial: BusinessInspection;
  hasWebsite: boolean;
}) {
  const [state, setState] = useState(initial);
  const [pending, startTransition] = useTransition();
  const router = useRouter();
  const active = state.active_job;
  const running = active !== null;

  useEffect(() => {
    if (!running) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const response = await fetch(`/api/businesses/${businessId}/inspection`, { cache: "no-store" });
        if (response.ok && !cancelled) {
          const next = (await response.json()) as BusinessInspection;
          setState(next);
          if (next.active_job === null) {
            router.refresh();
            return;
          }
        }
      } catch (cause) {
        console.error("[inspection] poll failed", cause);
      }
      if (!cancelled) timer = setTimeout(() => void poll(), POLL_MS);
    }

    timer = setTimeout(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [businessId, router, running]);

  function inspect() {
    startTransition(async () => {
      const result = await inspectBusinessAction(businessId);
      if (result.ok) setState((current) => ({ ...current, active_job: result.data }));
      else toast.error(result.message);
    });
  }

  const inspection = state.inspection;

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div className="space-y-1">
          <CardTitle>Website inspection</CardTitle>
          <CardDescription>Public information read from this business&apos;s website.</CardDescription>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={inspect}
          disabled={pending || running || !hasWebsite}
        >
          {pending || running ? <Loader2 className="animate-spin" /> : <ScanSearch />}
          {running ? "Inspecting…" : inspection ? "Inspect again" : "Inspect website"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-5">
        {running ? (
          <p role="status" className="text-sm text-muted-foreground">
            {active.status === "queued" ? "Queued. A background worker will pick this up shortly." : "Reading the website…"}
          </p>
        ) : null}
        {!hasWebsite ? <p className="text-sm text-muted-foreground">Add a website to this business to inspect it.</p> : null}
        {hasWebsite && !inspection && !running ? (
          <p className="text-sm text-muted-foreground">This website has not been inspected yet.</p>
        ) : null}

        {inspection ? (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <InspectionStatusBadge status={inspection.status} />
              {inspection.http_status ? <Badge>HTTP {inspection.http_status}</Badge> : null}
              {inspection.language ? <Badge>{inspection.language}</Badge> : null}
              <span className="text-xs text-subtle-foreground">Fetched {formatDateTime(inspection.fetched_at)}</span>
            </div>

            {inspection.error_message ? (
              <p role="alert" className="rounded-md border border-warning/30 bg-warning/8 px-3 py-2 text-sm text-muted-foreground">
                {inspection.error_message} This does not affect the business record.
              </p>
            ) : null}

            {inspection.title ? (
              <Section title="Title">
                <p className="text-sm">{inspection.title}</p>
              </Section>
            ) : null}
            {inspection.meta_description ? (
              <Section title="Meta description">
                <p className="text-sm text-muted-foreground">{inspection.meta_description}</p>
              </Section>
            ) : null}
            {inspection.canonical_url ? (
              <Section title="Canonical URL">
                <p className="truncate text-sm text-muted-foreground">{inspection.canonical_url}</p>
              </Section>
            ) : null}

            {inspection.emails.length > 0 ? (
              <Section title="Emails shown on the site">
                <ul className="space-y-1">
                  {inspection.emails.map((email) => (
                    <li key={email} className="flex items-center gap-2 text-sm">
                      <Mail aria-hidden className="size-3.5 text-subtle-foreground" /> {email}
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}
            {inspection.phones.length > 0 ? (
              <Section title="Telephone links">
                <ul className="space-y-1">
                  {inspection.phones.map((phone) => (
                    <li key={phone} className="flex items-center gap-2 text-sm">
                      <Phone aria-hidden className="size-3.5 text-subtle-foreground" /> {phone}
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}
            {inspection.social_links.length > 0 ? (
              <Section title="Social profiles">
                <ul className="flex flex-wrap gap-2">
                  {inspection.social_links.map((link) => (
                    <li key={String(link.url)}>
                      <a
                        href={String(link.url)}
                        target="_blank"
                        rel="noopener noreferrer nofollow"
                        className="inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs hover:border-border-strong"
                      >
                        <Share2 aria-hidden className="size-3" /> {humanize(String(link.network))}
                      </a>
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}
            {inspection.contact_links.length > 0 ? (
              <Section title="Contact pages">
                <ul className="space-y-1">
                  {inspection.contact_links.map((link) => (
                    <li key={String(link.url)}>
                      <a
                        href={String(link.url)}
                        target="_blank"
                        rel="noopener noreferrer nofollow"
                        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
                      >
                        {String(link.text ?? link.url)} <ExternalLink aria-hidden className="size-3" />
                      </a>
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}
            {inspection.headings.length > 0 ? (
              <Section title="Heading structure">
                <ul className="space-y-0.5">
                  {inspection.headings.slice(0, 12).map((heading, index) => (
                    <li
                      key={index}
                      className="truncate text-sm text-muted-foreground"
                      style={{ paddingLeft: `${(Number(heading.level) - 1) * 0.75}rem` }}
                    >
                      <span className="mr-1.5 font-mono text-xs text-subtle-foreground">h{String(heading.level)}</span>
                      {String(heading.text)}
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
