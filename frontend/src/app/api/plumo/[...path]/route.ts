import { cookies } from "next/headers";
import type { NextRequest } from "next/server";
import { forwardQuery, isAllowedRoute, isSameOriginWrite } from "@/lib/api/routes";
import { SESSION_COOKIE, backendFetch, json, unavailable } from "@/lib/server/backend";

// Dashboard proxy (BFF): browser → this route → FastAPI with the service key and the operator's
// session. Only routes in lib/api/routes.ts pass; the business always comes from the session.
async function proxy(request: NextRequest, params: Promise<{ path: string[] }>) {
  const method = request.method.toUpperCase();
  const path = (await params).path.map(part => encodeURIComponent(part)).join("/");
  if (!isAllowedRoute(method, path)) return json(404, { error: "not_found", code: "not_found", message: "unknown route" });
  if (!isSameOriginWrite(method, request.headers.get("origin"), request.headers.get("host"), request.headers.get("x-plumo-request"))) {
    return json(403, { error: "forbidden", code: "forbidden", message: "cross-site request" });
  }
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return json(401, { error: "not_authenticated", code: "not_authenticated", message: "sign in to continue" });
  const body = method === "GET" ? undefined : await request.text();
  if (body !== undefined && body.length > 100_000) return json(413, { error: "invalid_message", code: "invalid_message", message: "body is too large" });
  let response: Response;
  try {
    response = await backendFetch(`${path}${method === "GET" ? forwardQuery(request.nextUrl.searchParams) : ""}`, { method, body, token });
  } catch {
    return unavailable();
  }
  const text = await response.text();
  return new Response(text || null, {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") ?? "application/json", "cache-control": "no-store" },
  });
}

type Context = { params: Promise<{ path: string[] }> };
export const GET = (request: NextRequest, { params }: Context) => proxy(request, params);
export const POST = (request: NextRequest, { params }: Context) => proxy(request, params);
export const PATCH = (request: NextRequest, { params }: Context) => proxy(request, params);
