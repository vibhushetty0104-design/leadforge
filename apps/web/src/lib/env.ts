/**
 * Environment access (server side, read at request time).
 *
 * Supabase settings are deliberately *not* NEXT_PUBLIC_* variables: those are
 * inlined at build time, which would bake configuration into the image. The
 * server reads them at runtime and passes the public URL and publishable key
 * to browser components as props. The service-role key is never read here.
 */

export type SupabasePublicConfig = { url: string; key: string };

function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

export function getSupabaseConfig(): SupabasePublicConfig | null {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_PUBLISHABLE_KEY ?? process.env.SUPABASE_ANON_KEY;
  if (!url || !key || !isHttpUrl(url)) return null;
  return { url, key };
}

/** Names of missing configuration values, for setup guidance in the UI. */
export function missingConfiguration(): string[] {
  const missing: string[] = [];
  if (!getSupabaseConfig()) {
    missing.push("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY");
  }
  if (!getApiBaseUrl()) missing.push("API_BASE_URL");
  return missing;
}

/** Server-side base URL of the FastAPI service (never exposed to the browser). */
export function getApiBaseUrl(): string | null {
  const value = process.env.API_BASE_URL;
  if (!value || !isHttpUrl(value)) return null;
  return value.replace(/\/+$/, "");
}
