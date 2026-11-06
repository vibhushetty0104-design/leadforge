"use client";

import { FileUp, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { formatBytes, MAX_UPLOAD_BYTES, validateCsvFile } from "@/lib/csv";
import { cn } from "@/lib/utils";

export function CsvDropzone() {
  const inputId = useId();
  const router = useRouter();
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function upload(file: File) {
    const problem = validateCsvFile(file);
    setError(problem);
    if (problem) return;

    setUploading(file.name);
    try {
      const response = await fetch(`/api/imports?filename=${encodeURIComponent(file.name)}`, {
        method: "POST",
        headers: { "Content-Type": "text/csv" },
        body: file,
      });
      const body = (await response.json()) as { id?: string; error?: { message?: string } };
      if (!response.ok || !body.id) {
        setError(body.error?.message ?? "The upload failed. Try again.");
        return;
      }
      router.push(`/discovery/imports/${body.id}`);
    } catch {
      setError("The upload failed. Check your connection and try again.");
    } finally {
      setUploading(null);
    }
  }

  return (
    <div className="space-y-2">
      <label
        htmlFor={inputId}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const file = event.dataTransfer.files[0];
          if (file) void upload(file);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-6 py-10 text-center transition-colors focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring",
          dragging ? "border-primary bg-primary/10" : "border-border-strong hover:bg-muted/40",
        )}
      >
        <span className="rounded-full bg-primary/10 p-3 ring-1 ring-primary/20">
          {uploading ? (
            <Loader2 aria-hidden className="size-5 animate-spin text-primary-hover" />
          ) : (
            <FileUp aria-hidden className="size-5 text-primary-hover" />
          )}
        </span>
        <span>
          <span className="block text-sm font-medium">
            {uploading ? `Uploading ${uploading}…` : "Drop a CSV here, or choose a file"}
          </span>
          <span className="mt-1 block text-xs text-subtle-foreground">
            Up to {formatBytes(MAX_UPLOAD_BYTES)}. Nothing is saved until you review and confirm.
          </span>
        </span>
        <input
          id={inputId}
          type="file"
          accept=".csv,text/csv"
          aria-label="Choose a CSV file"
          className="sr-only"
          disabled={uploading !== null}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void upload(file);
          }}
        />
      </label>
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
