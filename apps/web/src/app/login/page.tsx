import { Settings2 } from "lucide-react";
import type { Metadata } from "next";
import { connection } from "next/server";

import { LoginForm } from "@/components/auth/login-form";
import { LogoMark } from "@/components/layout/logo";
import { Card } from "@/components/ui/card";
import { getSupabaseConfig, missingConfiguration } from "@/lib/env";

export const metadata: Metadata = { title: "Sign in" };

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function LoginPage({ searchParams }: { searchParams: SearchParams }) {
  await connection(); // configuration is read at request time, not baked in at build
  const params = await searchParams;
  const next = typeof params.next === "string" ? params.next : undefined;
  const authError = typeof params.error === "string" ? params.error : undefined;
  const config = getSupabaseConfig();
  const missing = missingConfiguration();

  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-3 text-center">
          <LogoMark className="size-10" />
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Welcome to LEADFORGE</h1>
            <p className="mt-1 text-sm text-muted-foreground">Prospect intelligence for agencies and freelancers.</p>
          </div>
        </div>
        <Card className="p-6">
          {authError ? (
            <p role="alert" className="mb-4 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
              {authError === "callback" ? "That sign-in link is invalid or has expired." : "Sign-in failed."}
            </p>
          ) : null}
          {config && missing.length === 0 ? (
            <LoginForm config={config} next={next} />
          ) : (
            <div className="space-y-3 text-sm">
              <div className="flex items-center gap-2 font-medium">
                <Settings2 className="size-4 text-warning" /> Setup required
              </div>
              <p className="text-muted-foreground">
                Authentication is not configured for this deployment. Set these variables in{" "}
                <code className="font-mono text-xs">apps/web/.env.local</code> and restart:
              </p>
              <ul className="space-y-1 font-mono text-xs text-foreground">
                {missing.map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
              <p className="text-muted-foreground">See docs/DEPLOYMENT.md for step-by-step instructions.</p>
            </div>
          )}
        </Card>
      </div>
    </main>
  );
}
