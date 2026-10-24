import { cookies } from "next/headers";
import type { NextRequest } from "next/server";
import { isSameOriginWrite } from "@/lib/api/routes";
import { SESSION_COOKIE, backendFetch, json } from "@/lib/server/backend";

export async function POST(request: NextRequest) {
  if (!isSameOriginWrite("POST", request.headers.get("origin"), request.headers.get("host"), request.headers.get("x-plumo-request"))) {
    return json(403, { error: "forbidden", code: "forbidden", message: "cross-site request" });
  }
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  if (token) {
    // The session is revoked on the server; the cookie goes away even if that call fails.
    await backendFetch("auth/logout", { method: "POST", token }).catch(() => null);
  }
  store.delete(SESSION_COOKIE);
  return new Response(null, { status: 204 });
}
