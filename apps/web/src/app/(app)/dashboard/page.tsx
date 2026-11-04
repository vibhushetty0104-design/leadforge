import type { BusinessStatus, DashboardSummary } from "@leadforge/shared";
import { BUSINESS_STATUSES } from "@leadforge/shared";
import {
  BellRing,
  Building2,
  Gauge,
  MailCheck,
  Plus,
  ScanSearch,
  Target,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { MetricCard } from "@/components/data/metric-card";
import { PageHeader } from "@/components/data/page-header";
import { EmptyState, ErrorState, SeedDataBanner } from "@/components/data/states";
import { BusinessStatusBadge } from "@/components/data/status-badge";
import { resolveOrgViewer } from "@/components/layout/org-gate";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate, formatDateTime, formatNumber, humanize } from "@/lib/format";
import { orgRequest } from "@/lib/viewer";

export const metadata: Metadata = { title: "Dashboard" };

const PIPELINE = ["qualified", "contacted", "engaged"] as const satisfies readonly BusinessStatus[];

export default async function DashboardPage() {
  const gate = await resolveOrgViewer();
  if (!gate.ok) return gate.fallback;
  const { viewer } = gate;

  const result = await orgRequest<DashboardSummary>(viewer, "/api/v1/dashboard/summary");
  if (!result.ok) {
    return (
      <div className="space-y-6">
        <PageHeader title="Dashboard" />
        <ErrorState title="Could not load dashboard metrics" error={result.error} />
      </div>
    );
  }
  const s = result.data;
  const byStatus = s.businesses.by_status;
  const inPipeline = PIPELINE.reduce((sum, status) => sum + (byStatus[status] ?? 0), 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description={`Live overview of ${s.organization.name}. Updated ${formatDateTime(s.generated_at)}.`}
        actions={
          <Button asChild>
            <Link href="/leads?new=1">
              <Plus /> Add business
            </Link>
          </Button>
        }
      />
      {s.organization.is_development_seed ? <SeedDataBanner /> : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <MetricCard
          label="Businesses"
          icon={Building2}
          value={formatNumber(s.businesses.total)}
          hint={`${formatNumber(s.businesses.added_last_30_days)} added in the last 30 days`}
        />
        <MetricCard
          label="Active pipeline"
          icon={Target}
          accent="blue"
          value={formatNumber(inPipeline)}
          hint="Qualified, contacted or engaged"
        />
        <MetricCard
          label="Average lead score"
          icon={Gauge}
          accent="teal"
          value={s.scores.average_latest_score === null ? "—" : formatNumber(s.scores.average_latest_score)}
          hint={
            s.scores.scored_businesses === 0
              ? "No businesses scored yet"
              : `Across ${formatNumber(s.scores.scored_businesses)} scored businesses`
          }
        />
        <MetricCard
          label="Website audits"
          icon={ScanSearch}
          accent="violet"
          value={formatNumber(s.audits.completed)}
          hint={`${formatNumber(s.audits.in_progress)} in progress · ${formatNumber(s.audits.failed)} failed`}
        />
        <MetricCard
          label="Follow-ups open"
          icon={BellRing}
          accent="amber"
          value={formatNumber(s.follow_ups.open)}
          hint={`${formatNumber(s.follow_ups.overdue)} overdue`}
        />
        <MetricCard
          label="Drafts awaiting review"
          icon={MailCheck}
          accent="blue"
          value={formatNumber(s.outreach.drafts_awaiting_review)}
          hint={`${formatNumber(s.outreach.active_campaigns)} active campaigns`}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Recently added</CardTitle>
            <CardDescription>The newest businesses in this organization.</CardDescription>
          </CardHeader>
          <CardContent className="pt-3">
            {s.recent_businesses.length === 0 ? (
              <EmptyState
                icon={Building2}
                title="No businesses yet"
                description="Add your first prospect to start building the pipeline."
                action={
                  <Button asChild variant="secondary" size="sm">
                    <Link href="/leads?new=1">
                      <Plus /> Add business
                    </Link>
                  </Button>
                }
              />
            ) : (
              <ul className="divide-y divide-border/70">
                {s.recent_businesses.map((b) => (
                  <li key={b.id} className="flex items-center justify-between gap-3 py-3">
                    <div className="min-w-0">
                      <Link href={`/leads/${b.id}`} className="block truncate text-sm font-medium hover:text-primary-hover">
                        {b.name}
                      </Link>
                      <p className="truncate text-xs text-subtle-foreground">
                        {b.domain ?? "No website"} · added {formatDate(b.created_at)}
                      </p>
                    </div>
                    <BusinessStatusBadge status={b.status} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Pipeline by status</CardTitle>
            <CardDescription>Distribution of all businesses.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 pt-4">
            {BUSINESS_STATUSES.map((status) => {
              const count = byStatus[status] ?? 0;
              const pct = s.businesses.total ? (count / s.businesses.total) * 100 : 0;
              return (
                <div key={status} className="grid grid-cols-[6.5rem_1fr_2.5rem] items-center gap-3 text-sm">
                  <span className="text-muted-foreground">{humanize(status)}</span>
                  <div className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden>
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-primary to-info transition-[width] duration-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-right tabular-nums">{formatNumber(count)}</span>
                </div>
              );
            })}
            <div className="mt-5 grid grid-cols-2 gap-2 border-t border-border pt-4 text-xs sm:grid-cols-4">
              {(["queued", "running", "completed", "failed"] as const).map((status) => (
                <div key={status} className="rounded-md bg-muted/50 px-2.5 py-2">
                  <p className="text-subtle-foreground">{humanize(status)} jobs</p>
                  <p className="mt-0.5 text-sm font-medium tabular-nums">{formatNumber(s.jobs[status] ?? 0)}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
