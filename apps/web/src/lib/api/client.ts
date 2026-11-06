import "server-only";

import type { ErrorResponse } from "@leadforge/shared";

import { getApiBaseUrl } from "@/lib/env";

export type ApiFailure = {
  status: number;
  code: string;
  message: string;
  details?: unknown;
  requestId?: string | null;
};

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiFailure };

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  token?: string;
  organizationId?: string;
  body?: unknown;
  query?: Record<string, string | number | undefined>;
};

const TIMEOUT_MS = 10_000;

function isErrorResponse(value: unknown): value is ErrorResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as { error: unknown }).error === "object"
  );
}

/**
 * Server-side call to the LEADFORGE API. Never throws for HTTP or network
 * failures: callers receive a typed failure and must render or report it.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<ApiResult<T>> {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    return {
      ok: false,
      error: { status: 0, code: "api_not_configured", message: "API_BASE_URL is not configured." },
    };
  }

  const url = new URL(`${baseUrl}${path}`);
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  if (options.organizationId) headers["X-Organization-Id"] = options.organizationId;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (cause) {
    console.error("[api] request failed", { path, cause });
    return {
      ok: false,
      error: {
        status: 0,
        code: "api_unreachable",
        message: "The LEADFORGE API could not be reached. Check that it is running.",
      },
    };
  }

  if (response.status === 204) return { ok: true, data: undefined as T };

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch (cause) {
    console.error("[api] invalid JSON response", { path, status: response.status, cause });
  }

  if (response.ok) {
    if (payload === null) {
      return {
        ok: false,
        error: { status: response.status, code: "invalid_response", message: "Unexpected API response." },
      };
    }
    return { ok: true, data: payload as T };
  }

  if (isErrorResponse(payload)) {
    return {
      ok: false,
      error: {
        status: response.status,
        code: payload.error.code,
        message: payload.error.message,
        details: payload.error.details,
        requestId: payload.error.request_id,
      },
    };
  }
  return {
    ok: false,
    error: { status: response.status, code: "http_error", message: `API returned ${response.status}.` },
  };
}

/** Forward a request whose body or response is a stream (CSV upload and export). */
export async function apiForward(
  path: string,
  init: { method: "POST"; token: string; organizationId: string; contentType: string; body: BodyInit | null },
): Promise<Response> {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) throw new Error("API_BASE_URL is not configured.");
  return fetch(`${baseUrl}${path}`, {
    method: init.method,
    headers: {
      Authorization: `Bearer ${init.token}`,
      "X-Organization-Id": init.organizationId,
      "Content-Type": init.contentType,
    },
    body: init.body,
    cache: "no-store",
    // Required by fetch when the body is a stream.
    ...(init.body instanceof ReadableStream ? { duplex: "half" } : {}),
  } as RequestInit);
}
