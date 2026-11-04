"use client";

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import type { SupabasePublicConfig } from "@/lib/env";

let browserClient: SupabaseClient | null = null;

/** Browser client for sign-in flows. Config is passed from the server to keep env access in one place. */
export function getSupabaseBrowserClient(config: SupabasePublicConfig): SupabaseClient {
  browserClient ??= createBrowserClient(config.url, config.key);
  return browserClient;
}
