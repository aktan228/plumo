import { cookies } from "next/headers";
import type { NextRequest } from "next/server";
import { isSameOriginWrite } from "@/lib/api/routes";
import { SESSION_COOKIE, backendFetch, json, unavailable } from "@/lib/server/backend";

// Sign-in: the browser sends email and password here; the session token returned by the
// backend goes into an HttpOnly cookie and never into the response body.
export async function POST(request: NextRequest) {
  if (!isSameOriginWrite("POST", request.headers.get("origin"), request.headers.get("host"), request.headers.get("x-plumo-request"))) {
    return json(403, { error: "forbidden", code: "forbidden", message: "cross-site request" });
  }
  let body: { email?: unknown; password?: unknown };
  try { body = await request.json(); } catch { return json(422, { error: "invalid_message", code: "invalid_message", message: "invalid body" }); }
  if (typeof body.email !== "string" || typeof body.password !== "string") {
    return json(422, { error: "invalid_message", code: "invalid_message", message: "email and password are required" });
  }
  let response: Response;
  try {
    response = await backendFetch("auth/login", { method: "POST", body: JSON.stringify({ email: body.email, password: body.password }) });
  } catch {
    return unavailable();
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) return json(response.status, data);
  const { token, expires_at: expiresAt, ...session } = data as { token: string; expires_at: string };
  (await cookies()).set({
    name: SESSION_COOKIE,
    value: token,
    httpOnly: true,
    sameSite: "lax",
    // Secure on HTTPS, including behind a TLS proxy or tunnel (cloudflared sets x-forwarded-proto).
    secure: request.nextUrl.protocol === "https:" || request.headers.get("x-forwarded-proto") === "https",
    path: "/",
    expires: new Date(expiresAt),
  });
  return json(200, { ...session, expires_at: expiresAt });
}
