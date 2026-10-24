import { emptyDraft, sourceFits, sourceUrl, type AgentDraft, type Source } from "./wizard-model.ts";
import type { PricingRequest } from "@/components/landing/pricing";

export type Snapshot = { step: number; settings: AgentDraft; sources: Source[]; channel: number; pricing: PricingRequest | null; entry: { kind: Source["kind"]; value: string; question: string } };
export type SavedWizard = { business_id: string; step: number; data: Omit<Snapshot, "step"> | null; version: number; completed_at: string | null; updated_at: string };
export const GUEST_KEY = "plumo-wizard-guest-v1";
export const MAX_WIZARD_BODY_BYTES = 2_000_000;

export function blankSnapshot(): Snapshot {
  return { step: 0, settings: { ...emptyDraft }, sources: [], channel: 0, pricing: null, entry: { kind: "website", value: "", question: "" } };
}
export function snapshotBody(snapshot: Snapshot, version: number) {
  const { step, ...data } = snapshot;
  return { version, step, data };
}
export function restoredSnapshot(row: SavedWizard): Snapshot {
  const blank = blankSnapshot();
  if (!row.data) return blank;
  return { step: row.step, settings: Object.fromEntries(Object.keys(blank.settings).map(key => [key, row.data!.settings[key as keyof AgentDraft] ?? blank.settings[key as keyof AgentDraft]])) as AgentDraft,
    sources: row.data.sources.map(source => ({ id: source.id, kind: source.kind, title: source.title, content: source.content, ...(source.question ? { question: source.question } : {}) })),
    channel: row.data.channel, pricing: row.data.pricing ? { choice: row.data.pricing.choice, volume: row.data.pricing.volume, billing: row.data.pricing.billing, voice: row.data.pricing.voice } : null, entry: row.data.entry ? { kind: row.data.entry.kind, value: row.data.entry.value, question: row.data.entry.question } : blank.entry };
}
export function guestSnapshot(raw: string | null): Snapshot | null {
  if (!raw || new TextEncoder().encode(raw).length > MAX_WIZARD_BODY_BYTES) return null;
  try {
    const value = JSON.parse(raw) as Snapshot;
    const d = value.settings;
    if (!value || !Number.isInteger(value.step) || value.step < 0 || value.step > 5 || !Number.isInteger(value.channel) || value.channel < 0 || value.channel > 4 || !d) return null;
    const bounds = { company: 200, description: 3000, audience: 2000, logoName: 255, name: 60, greeting: 1000, goal: 1500, fallback: 1000 } as const;
    for (const [key, max] of Object.entries(bounds)) if (typeof d[key as keyof typeof bounds] !== "string" || Array.from(d[key as keyof typeof bounds]).length > max) return null;
    if (!["sales", "support"].includes(d.purpose) || !["friendly", "formal"].includes(d.tone) || !["ru", "en"].includes(d.language) || !/^#[0-9a-f]{6}$/i.test(d.color)) return null;
    if (typeof d.logo !== "string" || d.logo.length > 1_333_400 || (d.logo && !/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(d.logo))) return null;
    if (!Array.isArray(value.sources) || new Set(value.sources.map(source => source.id)).size !== value.sources.length) return null;
    const accepted: Source[] = [];
    for (const source of value.sources) {
      if (!source || !/^[A-Za-z0-9_-]{1,80}$/.test(source.id) || !["website", "instagram", "text", "file", "faq"].includes(source.kind) || typeof source.title !== "string" || !source.title || source.title.length > 300 || typeof source.content !== "string" || !source.content.trim() || (source.question !== undefined && (typeof source.question !== "string" || source.question.length > 300))) return null;
      if ((source.kind === "faq" && !source.question?.trim()) || (["website", "instagram"].includes(source.kind) && !sourceUrl(source.content, source.kind === "instagram")) || !sourceFits(accepted, source)) return null;
      accepted.push(source);
    }
    if (!value.entry || !["website", "instagram", "text", "file", "faq"].includes(value.entry.kind) || typeof value.entry.value !== "string" || new TextEncoder().encode(value.entry.value).length > 100_000 || typeof value.entry.question !== "string" || value.entry.question.length > 300) return null;
    const p = value.pricing;
    if (p && (!["start", "business", "custom", "demo"].includes(p.choice) || !Number.isInteger(p.volume) || p.volume < 1000 || p.volume > 10000 || p.volume % 500 !== 0 || !["month", "quarter"].includes(p.billing) || typeof p.voice !== "boolean")) return null;
    // Project onto the public shape so browser storage cannot inject extra fields into an account save.
    const result = restoredSnapshot({ data: value, step: value.step } as unknown as SavedWizard);
    if (JSON.stringify(result).includes("\\u0000")) return null;
    return result;
  } catch { return null; }
}
