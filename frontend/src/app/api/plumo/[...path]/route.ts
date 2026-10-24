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
  let body: string | undefined;
  if (method !== "GET") {
    const maximum = path === "onboarding" ? 2_000_000 : 100_000;
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let total = 0;
    try {
      if (reader) while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        total += chunk.value.byteLength;
        if (total > maximum) {
          await reader.cancel();
          return json(413, { code: "invalid_message", message: "body is too large" });
        }
        chunks.push(chunk.value);
      }
      const joined = new Uint8Array(total);
      let offset = 0;
      for (const chunk of chunks) { joined.set(chunk, offset); offset += chunk.byteLength; }
      body = new TextDecoder("utf-8", { fatal: true }).decode(joined);
    } catch { return json(422, { code: "invalid_message", message: "invalid request body" }); }
    finally { reader?.releaseLock(); }
  }
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
