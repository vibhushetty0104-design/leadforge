import type { BusinessRead } from "@leadforge/shared";
import { ArrowLeft, ExternalLink } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { PageHeader } from "@/components/data/page-header";
import { ErrorState, SeedDataBanner } from "@/components/data/states";
import { BusinessStatusBadge } from "@/components/data/status-badge";
import { resolveOrgViewer } from "@/components/layout/org-gate";
import { DeleteBusinessButton } from "@/components/leads/delete-business-button";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime, humanize } from "@/lib/format";
import { orgRequest } from "@/lib/viewer";

export const metadata: Metadata = { title: "Business" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs font-medium tracking-wide text-subtle-foreground uppercase">{label}</dt>
      <dd className="text-sm">{children ?? "—"}</dd>
    </div>
  );
}

export default async function BusinessPage({ params }: { params: Promise<{ businessId: string }> }) {
  const { businessId } = await params;
  if (!UUID.test(businessId)) notFound();

  const gate = await resolveOrgViewer();
  if (!gate.ok) return gate.fallback;
  const { viewer } = gate;

  const result = await orgRequest<BusinessRead>(viewer, `/api/v1/businesses/${businessId}`);
  if (!result.ok) {
    if (result.error.status === 404) notFound();
    return <ErrorState title="Could not load this business" error={result.error} />;
  }
  const b = result.data;
  const canDelete = viewer.membership.role === "owner" || viewer.membership.role === "admin";

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2">
        <Link href="/leads">
          <ArrowLeft /> All leads
        </Link>
      </Button>
      <PageHeader
        title={b.name}
        description={
          b.website_url ? (
            <a href={b.website_url} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 hover:text-foreground">
              {b.website_url} <ExternalLink aria-hidden className="size-3.5" />
            </a>
          ) : (
            "No website recorded"
          )
        }
        actions={
          canDelete ? <DeleteBusinessButton businessId={b.id} businessName={b.name} redirectTo="/leads" /> : null
        }
      />
      {b.source === "development_seed" ? <SeedDataBanner /> : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <Field label="Status">
                <BusinessStatusBadge status={b.status} />
              </Field>
              <Field label="Industry">{b.industry}</Field>
              <Field label="Location">
                {[b.city, b.region, b.country_code].filter(Boolean).join(", ") || null}
              </Field>
              <Field label="Phone">{b.phone}</Field>
              <Field label="Source">{humanize(b.source)}</Field>
              <Field label="Domain">{b.domain}</Field>
              <div className="sm:col-span-2">
                <Field label="Notes">
                  {b.notes ? <p className="whitespace-pre-wrap text-muted-foreground">{b.notes}</p> : null}
                </Field>
              </div>
            </dl>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Record</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-4">
              <Field label="Created">{formatDateTime(b.created_at)}</Field>
              <Field label="Last updated">{formatDateTime(b.updated_at)}</Field>
              <Field label="Website audit">
                <span className="text-muted-foreground">
                  Automated audits arrive in Phase 2. No audit data exists for this business yet.
                </span>
              </Field>
            </dl>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
