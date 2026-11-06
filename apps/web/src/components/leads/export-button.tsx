"use client";

import type { BusinessExportRequest } from "@leadforge/shared";
import { Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

export function ExportButton({ request, label = "Export CSV" }: { request: BusinessExportRequest; label?: string }) {
  const [pending, setPending] = useState(false);

  async function download() {
    setPending(true);
    try {
      const response = await fetch("/api/businesses/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { error?: { message?: string } } | null;
        toast.error(body?.error?.message ?? "The export failed.");
        return;
      }
      const name = /filename="([^"]+)"/.exec(response.headers.get("content-disposition") ?? "")?.[1];
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = name ?? "leadforge-businesses.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("The export failed. Check your connection and try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Button type="button" variant="secondary" onClick={() => void download()} disabled={pending}>
      {pending ? <Loader2 className="animate-spin" /> : <Download />}
      {label}
    </Button>
  );
}
