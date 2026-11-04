import type { Snapshot } from "../create-agent/wizard-persistence.ts";

export function publicationGaps(snapshot: Snapshot) {
  const required = ["company", "description", "name", "greeting", "goal", "fallback"] as const;
  return {
    fields: required.filter(key => !snapshot.settings[key].trim()),
    materials: snapshot.sources.length === 0,
    pendingSource: Boolean(snapshot.entry.value.trim() || snapshot.entry.question.trim()),
  };
}

export function setupCanPublish(snapshot: Snapshot) {
  const gaps = publicationGaps(snapshot);
  return gaps.fields.length === 0 && !gaps.materials && !gaps.pendingSource;
}
