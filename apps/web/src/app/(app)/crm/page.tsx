import { AlarmClock, BellRing, Handshake, UsersRound } from "lucide-react";
import type { Metadata } from "next";

import { MetricCard } from "@/components/data/metric-card";
import { RoadmapSection } from "@/components/data/roadmap-section";
import { formatNumber } from "@/lib/format";

export const metadata: Metadata = { title: "CRM" };

export default function CrmPage() {
  return (
    <RoadmapSection
      title="CRM"
      phase="Phase 4"
      icon={UsersRound}
      description="Track conversations, follow-ups and deal stages for every prospect."
      planned={[
        "Kanban pipeline by lead status with drag-and-drop updates",
        "Activity timeline: notes, calls, meetings and emails per business",
        "Follow-up reminders with due dates and overdue alerts",
        "Contact management with primary-contact selection",
      ]}
      metrics={(s) => (
        <>
          <MetricCard label="Engaged prospects" icon={Handshake} accent="teal" value={formatNumber(s.businesses.by_status.engaged ?? 0)} />
          <MetricCard label="Open follow-ups" icon={BellRing} accent="blue" value={formatNumber(s.follow_ups.open)} />
          <MetricCard label="Overdue follow-ups" icon={AlarmClock} accent="amber" value={formatNumber(s.follow_ups.overdue)} />
        </>
      )}
    />
  );
}
