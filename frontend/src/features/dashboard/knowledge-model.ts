import { sourceFits, sourceUrl, type Source } from "../create-agent/wizard-model.ts";

export type MaterialIssue = "title" | "content" | "question" | "url" | "limits";

export function materialIssue(source: Source, sources: Source[]): MaterialIssue | null {
  if (!source.title.trim() || Array.from(source.title).length > 300 || source.title.includes("\0")) return "title";
  if (!source.content.trim() || source.content.includes("\0")) return "content";
  if (source.kind === "faq" && (!source.question?.trim() || Array.from(source.question).length > 300 || source.question.includes("\0"))) return "question";
  if ((source.kind === "website" || source.kind === "instagram") && !sourceUrl(source.content, source.kind === "instagram")) return "url";
  if (!sourceFits(sources.filter(item => item.id !== source.id), source)) return "limits";
  return null;
}

export function updateMaterial(sources: Source[], source: Source): Source[] {
  return sources.some(item => item.id === source.id) ? sources.map(item => item.id === source.id ? source : item) : [...sources, source];
}
