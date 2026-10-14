export type WhatsAppDraft = {
  method: "business-app" | "cloud";
  app: "business" | "personal" | null;
  migrated: boolean;
  payment: "meta" | "plumo" | null;
};
export const initialWhatsAppDraft: WhatsAppDraft = { method: "business-app", app: null, migrated: false, payment: null };

export function canAdvanceWhatsApp(step: number, draft: WhatsAppDraft): boolean {
  if (step === 0) return true;
  if (step === 1) return draft.app === "business" || (draft.app === "personal" && draft.migrated);
  if (step === 2) return draft.payment !== null;
  return false;
}
export function nextWhatsAppStep(step: number, draft: WhatsAppDraft): number {
  if (!canAdvanceWhatsApp(step, draft)) return step;
  return step === 0 && draft.method === "cloud" ? 2 : step + 1;
}
export function previousWhatsAppStep(step: number, draft: WhatsAppDraft): number {
  return step === 2 && draft.method === "cloud" ? 0 : Math.max(0, step - 1);
}
