import { Ban, MailCheck, Send } from "lucide-react";
import type { Metadata } from "next";

import { MetricCard } from "@/components/data/metric-card";
import { RoadmapSection } from "@/components/data/roadmap-section";
import { formatNumber } from "@/lib/format";

export const metadata: Metadata = { title: "Campaigns" };

export default function CampaignsPage() {
  return (
    <RoadmapSection
      title="Campaigns"
      phase="Phase 4"
      icon={Send}
      description="Group prospects and prepare personalised, human-reviewed outreach."
      planned={[
        "Create campaigns and add qualified businesses",
        "Draft emails from audit findings using templates — no paid AI APIs",
        "Review and approve every draft before it leaves your own mail client",
        "Suppression list enforcement for unsubscribes, bounces and do-not-contact",
      ]}
      metrics={(s) => (
        <>
          <MetricCard label="Active campaigns" icon={Send} value={formatNumber(s.outreach.active_campaigns)} />
          <MetricCard label="Drafts awaiting review" icon={MailCheck} accent="blue" value={formatNumber(s.outreach.drafts_awaiting_review)} />
          <MetricCard label="Suppressed contacts" icon={Ban} accent="amber" value={formatNumber(s.outreach.suppressions)} />
        </>
      )}
    />
  );
}
