import type { HealthResponse } from "@leadforge/shared";
import { CheckCircle2, LogOut, XCircle } from "lucide-react";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import { signOutAction } from "@/app/actions";
import { PageHeader } from "@/components/data/page-header";
import { ErrorState } from "@/components/data/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiRequest } from "@/lib/api/client";
import { formatDate, humanize } from "@/lib/format";
import { requireViewer } from "@/lib/viewer";

export const metadata: Metadata = { title: "Settings" };

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="min-w-0 truncate text-sm">{children}</dd>
    </div>
  );
}

export default async function SettingsPage() {
  const viewer = await requireViewer();
  const health = await apiRequest<HealthResponse>("/health");

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Your account, organizations and system status." />
      {viewer.kind === "error" ? <ErrorState title="Could not load your account" error={viewer.error} /> : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {viewer.kind === "ready" ? (
          <>
            <Card>
              <CardHeader>
                <CardTitle>Profile</CardTitle>
                <CardDescription>Managed by Supabase Auth.</CardDescription>
              </CardHeader>
              <CardContent>
                <dl className="divide-y divide-border/70">
                  <Row label="Email">{viewer.me.profile.email ?? "—"}</Row>
                  <Row label="Name">{viewer.me.profile.full_name ?? "—"}</Row>
                  <Row label="User ID">
                    <code className="font-mono text-xs text-muted-foreground">{viewer.me.profile.id}</code>
                  </Row>
                </dl>
                <form action={signOutAction} className="mt-4">
                  <Button type="submit" variant="secondary">
                    <LogOut /> Sign out
                  </Button>
                </form>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Organizations</CardTitle>
                <CardDescription>Switch the active organization from the top bar.</CardDescription>
              </CardHeader>
              <CardContent>
                {viewer.me.memberships.length === 0 ? (
                  <p className="text-sm text-muted-foreground">You are not a member of any organization yet.</p>
                ) : (
                  <ul className="divide-y divide-border/70">
                    {viewer.me.memberships.map((m) => (
                      <li key={m.organization.id} className="flex items-center justify-between gap-3 py-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{m.organization.name}</p>
                          <p className="text-xs text-subtle-foreground">
                            {humanize(m.role)} · since {formatDate(m.organization.created_at)}
                          </p>
                        </div>
                        <div className="flex shrink-0 gap-1.5">
                          {m.organization.is_development_seed ? <Badge tone="amber">Seed data</Badge> : null}
                          {m.organization.id === viewer.membership?.organization.id ? (
                            <Badge tone="violet">Active</Badge>
                          ) : null}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>System status</CardTitle>
            <CardDescription>Live check of the API and its database connection.</CardDescription>
          </CardHeader>
          <CardContent>
            {health.ok ? (
              <dl className="divide-y divide-border/70">
                <Row label="API">
                  <span className="inline-flex items-center gap-1.5 text-success">
                    <CheckCircle2 className="size-4" /> {health.data.status === "ok" ? "Operational" : "Degraded"}
                  </span>
                </Row>
                <Row label="Database">
                  {health.data.database === "ok" ? (
                    <span className="inline-flex items-center gap-1.5 text-success">
                      <CheckCircle2 className="size-4" /> Connected
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-danger">
                      <XCircle className="size-4" /> Unavailable
                    </span>
                  )}
                </Row>
                <Row label="API version">{health.data.version}</Row>
              </dl>
            ) : (
              <p className="inline-flex items-center gap-1.5 text-sm text-danger">
                <XCircle className="size-4" /> {health.error.message}
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
