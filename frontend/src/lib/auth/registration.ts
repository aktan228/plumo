// Shared browser/server registration boundaries; the backend additionally validates email syntax.
export const REGISTRATION_PASSWORD_MIN = 10;
export const REGISTRATION_PASSWORD_MAX = 128;
export type RegistrationIssue = "name" | "email" | "password" | "locale";

export function registrationIssue(value: unknown): RegistrationIssue | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "name";
  const body = value as Record<string, unknown>;
  if (typeof body.name !== "string" || !body.name.trim() || Array.from(body.name.trim()).length > 100 || /[\u0000-\u001f\u007f]/.test(body.name)) return "name";
  if (typeof body.email !== "string" || body.email.trim().length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.email.trim())) return "email";
  if (typeof body.password !== "string" || !body.password.trim() || Array.from(body.password).length < REGISTRATION_PASSWORD_MIN || Array.from(body.password).length > REGISTRATION_PASSWORD_MAX) return "password";
  if (body.locale !== undefined && body.locale !== "ru" && body.locale !== "en") return "locale";
  return null;
}

export function safeNextPath(value: string | null, fallback = "/dashboard"): string {
  if (!value?.startsWith("/")) return fallback;
  try {
    const url = new URL(value, "https://plumo.invalid");
    return url.origin === "https://plumo.invalid" ? url.pathname + url.search + url.hash : fallback;
  } catch { return fallback; }
}
