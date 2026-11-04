"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Mail } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { FieldError, Input, Label } from "@/components/ui/input";
import type { SupabasePublicConfig } from "@/lib/env";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

const schema = z.object({
  email: z.email("Enter a valid email address"),
  password: z.string().min(8, "At least 8 characters").max(72),
});
type Values = z.infer<typeof schema>;
type Mode = "sign-in" | "sign-up";

/** Only allow same-origin relative redirects after sign-in. */
function safeNext(next: string | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
}

export function LoginForm({ config, next }: { config: SupabasePublicConfig; next?: string }) {
  const [mode, setMode] = useState<Mode>("sign-in");
  const [magicPending, setMagicPending] = useState(false);
  const router = useRouter();
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });
  const { errors, isSubmitting } = form.formState;

  async function onSubmit({ email, password }: Values) {
    const supabase = getSupabaseBrowserClient(config);
    if (mode === "sign-in") {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) {
        toast.error(error.message);
        return;
      }
      router.replace(safeNext(next));
      router.refresh();
      return;
    }
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    });
    if (error) {
      toast.error(error.message);
      return;
    }
    if (data.session) {
      router.replace("/dashboard");
      router.refresh();
    } else {
      toast.success("Check your inbox to confirm your email address.");
    }
  }

  async function sendMagicLink() {
    const valid = await form.trigger("email");
    if (!valid) return;
    setMagicPending(true);
    const supabase = getSupabaseBrowserClient(config);
    const redirect = new URL("/auth/callback", window.location.origin);
    redirect.searchParams.set("next", safeNext(next));
    const { error } = await supabase.auth.signInWithOtp({
      email: form.getValues("email"),
      options: { emailRedirectTo: redirect.toString(), shouldCreateUser: false },
    });
    setMagicPending(false);
    if (error) toast.error(error.message);
    else toast.success("Magic link sent. Check your inbox.");
  }

  return (
    <div className="space-y-6">
      <div role="tablist" aria-label="Authentication mode" className="grid grid-cols-2 rounded-lg bg-muted p-1">
        {(["sign-in", "sign-up"] as const).map((m) => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={mode === m}
            onClick={() => setMode(m)}
            className={cn(
              "rounded-md py-1.5 text-sm font-medium transition-colors",
              mode === m ? "bg-surface-raised text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {m === "sign-in" ? "Sign in" : "Create account"}
          </button>
        ))}
      </div>

      <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" aria-invalid={Boolean(errors.email)} {...form.register("email")} />
          <FieldError message={errors.email?.message} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
            aria-invalid={Boolean(errors.password)}
            {...form.register("password")}
          />
          <FieldError message={errors.password?.message} />
        </div>
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? <Loader2 className="animate-spin" /> : null}
          {mode === "sign-in" ? "Sign in" : "Create account"}
        </Button>
      </form>

      {mode === "sign-in" ? (
        <>
          <div className="flex items-center gap-3 text-xs text-subtle-foreground">
            <span className="h-px flex-1 bg-border" /> or <span className="h-px flex-1 bg-border" />
          </div>
          <Button type="button" variant="secondary" className="w-full" onClick={sendMagicLink} disabled={magicPending}>
            {magicPending ? <Loader2 className="animate-spin" /> : <Mail />}
            Email me a sign-in link
          </Button>
        </>
      ) : null}
    </div>
  );
}
