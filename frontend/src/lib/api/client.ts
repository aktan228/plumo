// Browser client of the dashboard API. It only talks to our own Next.js server (/api/plumo/*),
// which adds the service key and the session; no token is ever visible to page code.

import type { ApiErrorBody } from "./types";

export class ApiError extends Error {
  status: number;
  code: string;
  correlationId: string | null;

  constructor(status: number, code: string, message: string, correlationId: string | null = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.correlationId = correlationId;
  }
  /** Not signed in or the session ended: the page should go to /login. */
  get unauthenticated() { return this.status === 401; }
  /** The server or the network is down, as opposed to a refused action. */
  get unavailable() { return this.status === 0 || this.status === 502 || this.status === 503 || this.status === 504; }
}

export function errorFrom(status: number, body: unknown): ApiError {
  const data = (body && typeof body === "object" ? body : {}) as ApiErrorBody;
  const code = data.code || data.error || (status === 0 ? "network_error" : `http_${status}`);
  return new ApiError(status, code, data.message || "", data.correlation_id ?? null);
}

type Options = { method?: "GET" | "POST" | "PATCH"; body?: unknown; query?: Record<string, string | number | undefined | null>; signal?: AbortSignal };

export async function api<T>(path: string, { method = "GET", body, query, signal }: Options = {}): Promise<T> {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  const url = `/api/plumo/${path}${search.size ? `?${search}` : ""}`;
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      signal,
      cache: "no-store",
      credentials: "same-origin",
      headers: { "content-type": "application/json", "x-plumo-request": "1" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw errorFrom(0, null);
  }
  const text = await response.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!response.ok) throw errorFrom(response.status, data);
  return data as T;
}

/** Redirect to sign-in when the session is gone; keep the current page to come back to. */
export function goToLogin() {
  if (typeof window !== "undefined") window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
}
