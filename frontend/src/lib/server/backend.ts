// Server-only access to the Plumo FastAPI backend. Never import from a client component:
// PLUMO_API_KEY is a server secret and must not reach the browser bundle.

import { cookies } from "next/headers";
import type { Session } from "@/lib/api/types";

if (typeof window !== "undefined") throw new Error("lib/server/backend is server-only");

export const SESSION_COOKIE = "plumo_session";

export function backendUrl(path: string): string {
  const base = (process.env.PLUMO_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
  return `${base}/api/v1/${path}`;
}

export async function backendFetch(path: string, init: { method?: string; body?: string; token?: string | null } = {}): Promise<Response> {
  const headers: Record<string, string> = { accept: "application/json" };
  if (init.body !== undefined) headers["content-type"] = "application/json";
  const key = process.env.PLUMO_API_KEY;
  if (key) headers["x-api-key"] = key;
  if (init.token) headers.authorization = `Bearer ${init.token}`;
  return fetch(backendUrl(path), { method: init.method ?? "GET", body: init.body, headers, cache: "no-store", signal: AbortSignal.timeout(30_000) });
}

export type SessionCheck = { state: "ok"; session: Session } | { state: "anonymous" } | { state: "unavailable" };

/** The signed-in operator, checked by the backend; used by server components to guard pages. */
export async function currentSession(): Promise<SessionCheck> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return { state: "anonymous" };
  try {
    const response = await backendFetch("auth/me", { token });
    if (response.status === 401) return { state: "anonymous" };
    if (!response.ok) return { state: "unavailable" };
    return { state: "ok", session: (await response.json()) as Session };
  } catch {
    return { state: "unavailable" };
  }
}

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
}

export function unavailable(): Response {
  return json(503, { error: "backend_unavailable", code: "backend_unavailable", message: "Plumo API is not reachable" });
}
