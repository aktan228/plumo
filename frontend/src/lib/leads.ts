// Pilot request from the website. Pure module: tests run it with plain Node.

export type LeadSource = "landing" | "wizard";
export type LeadPayload = {
  idempotency_key: string; source: LeadSource; name: string; company: string; email: string;
  message: string; plan: string; locale: "ru" | "en";
};

const text = (value: FormDataEntryValue | null, max: number) => String(value ?? "").trim().slice(0, max);

/** One key per filled form: a double click or a retry after a network error sends the same request. */
export function leadPayload(form: FormData, source: LeadSource, locale: "ru" | "en", key: string, plan = "", context = ""): LeadPayload {
  const message = [text(form.get("message"), 1500), context.trim()].filter(Boolean).join("\n\n").slice(0, 2000);
  return {
    idempotency_key: key, source, locale, plan: plan.slice(0, 200), message,
    name: text(form.get("name"), 100).replace(/\s+/g, " "), company: text(form.get("company"), 200).replace(/\s+/g, " "),
    email: text(form.get("email"), 254).toLowerCase(),
  };
}

export function leadKey(): string {
  return crypto.randomUUID().replaceAll("-", "");
}
