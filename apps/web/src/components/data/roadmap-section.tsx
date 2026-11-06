import type { DashboardSummary } from "@leadforge/shared";
import { CircleDashed, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { PageHeader } from "@/components/data/page-header";
import { EmptyState, ErrorState } from "@/components/data/states";
import { resolveOrgViewer } from "@/components/layout/org-gate";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { orgRequest } from "@/lib/viewer";

/**
 * Page for a section whose workflow ships in a later phase. It shows the real
 * counts that already exist in the database plus an honest statement of what
 * is planned. It deliberately renders no action buttons.
 */
export async function RoadmapSection({
  title,
  description,
  phase,
  icon,
  planned,
  metrics,
}: {
  title: string;
  description: string;
  phase: string;
  icon: LucideIcon;
  planned: string[];
  metrics: (summary: DashboardSummary) => ReactNode;
}) {
  const gate = await resolveOrgViewer();
  if (!gate.ok) return gate.fallback;
  const summary = await orgRequest<DashboardSummary>(gate.viewer, "/api/v1/dashboard/summary");

  return (
    <div className="space-y-6">
      <PageHeader title={title} description={description} actions={<Badge tone="violet">{phase}</Badge>} />
      {summary.ok ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">{metrics(summary.data)}</div>
      ) : (
        <ErrorState title="Could not load current counts" error={summary.error} />
      )}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <EmptyState
          className="lg:col-span-3"
          icon={icon}
          title={`${title} workflow is not available yet`}
          description={`The data model is in place and the counts above are live. The interactive workflow ships in ${phase}.`}
        />
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Planned for {phase}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2.5">
              {planned.map((item) => (
                <li key={item} className="flex gap-2.5 text-sm text-muted-foreground">
                  <CircleDashed aria-hidden className="mt-0.5 size-4 shrink-0 text-subtle-foreground" />
                  {item}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
