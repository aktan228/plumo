import type { NextRequest } from "next/server";
import { isSameOriginWrite } from "@/lib/api/routes";
import { backendFetch, json, unavailable } from "@/lib/server/backend";

const MAX_BYTES = 4096;

// Public form of the website: same-origin only, small body; the backend validates fields and limits per address.
export async function POST(request: NextRequest) {
  if (!isSameOriginWrite("POST", request.headers.get("origin"), request.headers.get("host"), request.headers.get("x-plumo-request"))) {
    return json(403, { code: "forbidden", message: "cross-site request" });
  }
  const body = await request.text().catch(() => null);
  if (body === null) return json(422, { code: "invalid_message", message: "invalid body" });
  if (new TextEncoder().encode(body).byteLength > MAX_BYTES) return json(413, { code: "body_too_large", message: "request body is too large" });
  const clientIp = (request.headers.get("x-forwarded-for")?.split(",")[0].trim() || request.headers.get("x-real-ip") || "unknown").slice(0, 64);
  let response: Response;
  try { response = await backendFetch("leads", { method: "POST", body, clientIp }); }
  catch (error) { return unavailable(error); }
  return json(response.status, await response.json().catch(() => ({})));
}
