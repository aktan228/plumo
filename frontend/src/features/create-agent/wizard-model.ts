export type Source = { id: string; kind: "website" | "instagram" | "text" | "file" | "faq"; title: string; content: string; question?: string };
export type AgentDraft = {
  purpose: "sales" | "support";
  company: string; description: string; audience: string;
  color: string; logo: string; logoName: string;
  name: string; tone: "friendly" | "formal"; language: "ru" | "en";
  greeting: string; goal: string; fallback: string;
};
export const MAX_SOURCE_BYTES = 100_000;
export const MAX_TOTAL_BYTES = 200_000;
export const MAX_SOURCES = 10;
export const emptyDraft: AgentDraft = { purpose: "sales", company: "", description: "", audience: "", color: "#2b55ff", logo: "", logoName: "", name: "Plumo", tone: "friendly", language: "ru", greeting: "", goal: "", fallback: "" };

export function sourceUrl(value: string, instagram = false): string | null {
  try {
    const url = new URL(/^[a-z][a-z\d+.-]*:/i.test(value.trim()) ? value.trim() : `https://${value.trim()}`);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || !url.hostname.includes(".") || /\s/.test(value)) return null;
    if (instagram && !/(^|\.)instagram\.com$/i.test(url.hostname)) return null;
    return url.href;
  } catch { return null; }
}

export function sourceFits(sources: Source[], source: Source): boolean {
  const size = (s: Source) => new TextEncoder().encode(s.content + (s.question ?? "")).length;
  return sources.length < MAX_SOURCES && size(source) <= MAX_SOURCE_BYTES && sources.reduce((sum, s) => sum + size(s), 0) + size(source) <= MAX_TOTAL_BYTES;
}

export function makeScript(draft: AgentDraft) {
  const ru = draft.language === "ru";
  return {
    greeting: ru ? `${draft.tone === "formal" ? "Добрый день" : "Здравствуйте"}! Я ${draft.name}, ИИ-ассистент ${draft.company}. Чем могу помочь?` : `${draft.tone === "formal" ? "Good day" : "Hello"}! I’m ${draft.name}, the AI assistant for ${draft.company}. How can I help?`,
    goal: ru ? (draft.purpose === "sales" ? "Выяснить потребность клиента и подготовить запрос менеджеру. Сделку завершает человек." : "Помочь по утверждённым ответам. Нерешённые вопросы передать сотруднику.") : (draft.purpose === "sales" ? "Understand the customer’s needs and prepare a request for a manager. A person closes the deal." : "Help using approved answers. Refer unresolved questions to the team."),
    fallback: ru ? "У меня пока нет подтверждённого ответа. Этот вопрос нужно уточнить у сотрудника." : "I don’t have a confirmed answer yet. Please check this question with our team.",
  };
}

const normalize = (value: string) => value.toLocaleLowerCase().replace(/[^\p{L}\p{N}\s]/gu, " ").replace(/\s+/g, " ").trim();
export function demoReply(question: string, draft: AgentDraft, sources: Source[]): { text: string; source?: string; handoff?: boolean } {
  const q = normalize(question);
  if (/\b(human|manager|person|operator)\b/i.test(q) || /(^|\s)(человек\S*|менеджер\S*|сотрудник\S*|оператор\S*)(\s|$)/u.test(q)) {
    return { text: draft.language === "ru" ? "Автоматические ответы в этом тестовом разговоре остановлены. В рабочем сценарии диалог продолжит сотрудник. Демо не отправляет уведомлений." : "Automatic replies in this test conversation are paused. In a live workflow, a team member would continue. This demo sends no notifications.", handoff: true };
  }
  const match = sources.find(source => source.kind === "faq" && normalize(source.question ?? "") === q);
  if (match) return { text: match.content, source: match.title };
  return { text: draft.fallback || makeScript(draft).fallback };
}

export function example(locale: "ru" | "en"): { draft: AgentDraft; sources: Source[] } {
  const ru = locale === "ru";
  return {
    draft: { ...emptyDraft, language: locale, company: ru ? "Ала-Тоо Дом · пример" : "Ala-Too Homes · example", description: ru ? "Вымышленное агентство недвижимости в Бишкеке. Помогаем выбрать квартиру и согласовать просмотр с менеджером." : "A fictional real estate agency in Bishkek. We help customers choose an apartment and request a viewing with a manager.", audience: ru ? "Семьи, которые ищут квартиру для проживания" : "Families looking for a home" },
    sources: [
      { id: "example-1", kind: "faq", title: ru ? "Варианты квартир" : "Apartments", question: ru ? "Какие квартиры есть?" : "What apartments are available?", content: ru ? "В нашем вымышленном примере есть двухкомнатная квартира 64 м² в южной части Бишкека. Что для вас важно при выборе?" : "Our fictional example includes a 64 m² two-room apartment in the south of Bishkek. What matters most to you?" },
      { id: "example-2", kind: "faq", title: ru ? "Просмотр" : "Viewing", question: ru ? "Можно посмотреть в субботу?" : "Can I view it on Saturday?", content: ru ? "Можно указать субботу как желаемое время. Менеджеру нужно проверить расписание и подтвердить просмотр. Сейчас запись не создана." : "You can request Saturday. A manager needs to check availability and confirm the viewing. No booking has been made." },
    ],
  };
}
