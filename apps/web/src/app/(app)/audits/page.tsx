import { CheckCircle2, Loader, ScanSearch, XCircle } from "lucide-react";
import type { Metadata } from "next";

import { MetricCard } from "@/components/data/metric-card";
import { RoadmapSection } from "@/components/data/roadmap-section";
import { formatNumber } from "@/lib/format";

export const metadata: Metadata = { title: "Audits" };

export default function AuditsPage() {
  return (
    <RoadmapSection
      title="Audits"
      phase="Phase 3"
      icon={ScanSearch}
      description="Measured website quality and conversion findings for each prospect."
      planned={[
        "Queue an audit for any business with a public website",
        "Playwright + BeautifulSoup checks: performance timings, SEO tags, accessibility basics, contact paths",
        "SSRF-safe fetching: DNS and redirect revalidation, private-network blocking, size and time limits",
        "Findings with severity, evidence and recommendations — never synthesised",
        "Lighthouse integration for lab performance metrics",
      ]}
      metrics={(s) => (
        <>
          <MetricCard label="Completed audits" icon={CheckCircle2} accent="teal" value={formatNumber(s.audits.completed)} />
          <MetricCard label="In progress" icon={Loader} accent="blue" value={formatNumber(s.audits.in_progress)} />
          <MetricCard label="Failed" icon={XCircle} accent="amber" value={formatNumber(s.audits.failed)} />
        </>
      )}
    />
  );
}
