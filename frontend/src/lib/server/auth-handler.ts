import { cookies } from "next/headers";
import type { NextRequest } from "next/server";
import { isSameOriginWrite } from "@/lib/api/routes";
import { registrationIssue, passwordIssue } from "@/lib/auth/registration";
import { SESSION_COOKIE, backendFetch, json, unavailable } from "./backend";

const MAX_AUTH_BYTES = 4096;

export async function handleAuth(request: NextRequest, mode: "login" | "register" | "verify-email" | "forgot-password" | "reset-password" | "resend-verification") {
  if (!isSameOriginWrite("POST", request.headers.get("origin"), request.headers.get("host"), request.headers.get("x-plumo-request"))) {
    return json(403, { code: "forbidden", message: "cross-site request" });
  }
  const reader = request.body?.getReader();
  let bytes = 0;
  let text = "";
  const decoder = new TextDecoder();
  try {
    if (!reader) throw new Error("empty body");
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      bytes += chunk.value.byteLength;
      if (bytes > MAX_AUTH_BYTES) {
        await reader.cancel();
        return json(413, { code: "body_too_large", message: "request body is too large" });
      }
      text += decoder.decode(chunk.value, { stream: true });
    }
    text += decoder.decode();
  } catch {
    return json(422, { code: "invalid_message", message: "invalid body" });
  } finally { reader?.releaseLock(); }

  let body: Record<string, unknown>;
  try {
    const parsed: unknown = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("invalid body");
    body = parsed as Record<string, unknown>;
  } catch { return json(422, { code: "invalid_message", message: "invalid body" }); }

  let payload: Record<string, unknown>;
  if (mode === "verify-email" || mode === "reset-password") {
    if (typeof body.token !== "string" || !/^[A-Za-z0-9_-]{43,128}$/.test(body.token) || (mode === "reset-password" && passwordIssue(body.password))) {
      return json(422, { code: "invalid_message", message: "invalid token or password" });
    }
    payload = { token: body.token, ...(mode === "reset-password" ? { password: body.password } : {}) };
  } else {
    if (mode === "register") {
      const issue = registrationIssue(body);
      if (issue) return json(422, { code: "invalid_registration", field: issue, message: "invalid registration fields" });
    } else if (typeof body.email !== "string" || body.email.length > 254 || (mode === "login" && (typeof body.password !== "string" || body.password.length > 200))) {
      return json(422, { code: "invalid_message", message: "invalid email or password" });
    }
    payload = { email: String(body.email).trim().toLowerCase(), ...(mode === "login" || mode === "register" ? { password: body.password } : { locale: body.locale ?? "ru" }), ...(mode === "register" ? { name: String(body.name).trim(), locale: body.locale ?? "ru" } : {}) };
  }
  // Vercel's forwarded client address is sent under our server key, never from a form field.
  const clientIp = (request.headers.get("x-forwarded-for")?.split(",")[0].trim() || request.headers.get("x-real-ip") || "unknown").slice(0, 64);
  let response: Response;
  try { response = await backendFetch(`auth/${mode}`, { method: "POST", body: JSON.stringify(payload), clientIp }); }
  catch (error) { return unavailable(error); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) return json(response.status, data);
  if (mode !== "login" && mode !== "verify-email") {
    if (mode === "reset-password") (await cookies()).delete(SESSION_COOKIE);
    return json(mode === "register" ? 201 : 200, data);
  }
  if (!data || typeof data !== "object" || typeof data.token !== "string" || !data.token || typeof data.expires_at !== "string" || !Number.isFinite(Date.parse(data.expires_at))) return unavailable();
  const { token, expires_at: expiresAt, ...session } = data;
  (await cookies()).set({
    name: SESSION_COOKIE, value: token, httpOnly: true, sameSite: "lax", path: "/",
    secure: request.nextUrl.protocol === "https:" || request.headers.get("x-forwarded-proto") === "https",
    expires: new Date(expiresAt),
  });
  return json(200, { ...session, expires_at: expiresAt });
}
