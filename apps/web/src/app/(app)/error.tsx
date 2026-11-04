"use client";

import { AlertTriangle, RotateCw } from "lucide-react";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";

export default function AppError({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  const digest =
    typeof error === "object" && error !== null && "digest" in error
      ? String((error as { digest: unknown }).digest)
      : null;

  return (
    <div role="alert" className="mx-auto mt-16 flex max-w-md flex-col items-center gap-4 text-center">
      <span className="rounded-full bg-danger/10 p-3 ring-1 ring-danger/30">
        <AlertTriangle aria-hidden className="size-5 text-danger" />
      </span>
      <div className="space-y-1">
        <h2 className="text-base font-semibold">This page failed to load</h2>
        <p className="text-sm text-muted-foreground">
          An unexpected error occurred. Details were logged on the server.
        </p>
        {digest ? <p className="font-mono text-xs text-subtle-foreground">ref {digest}</p> : null}
      </div>
      <Button variant="secondary" onClick={() => retry()}>
        <RotateCw /> Try again
      </Button>
    </div>
  );
}
