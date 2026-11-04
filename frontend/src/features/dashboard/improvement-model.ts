export const categories = ["incorrect_fact", "missing_answer", "handoff", "language_tone"] as const;
export type Category = typeof categories[number];
export type IssueStatus = "new" | "in_progress" | "fixed" | "verified";
export type AnswerSource = { message_id: string; test_session_id?: never; test_request_id?: never }
  | { message_id?: never; test_session_id: string; test_request_id: string };
export const categoryNames = {
  ru: { incorrect_fact: "Неверный факт", missing_answer: "Нет ответа", handoff: "Передача человеку", language_tone: "Язык или тон" },
  en: { incorrect_fact: "Incorrect fact", missing_answer: "Missing answer", handoff: "Handoff", language_tone: "Language or tone" },
};
export const statusNames = {
  ru: { new: "Новое", in_progress: "В работе", fixed: "Исправлено", verified: "Проверено" },
  en: { new: "New", in_progress: "In progress", fixed: "Fixed", verified: "Verified" },
};
export function improvementError(code: string, ru: boolean): string {
  const errors: Record<string, [string, string]> = {
    version_conflict: ["Замечание изменилось. Текст остался в поле; перечитайте карточку перед повтором.", "This issue changed. Your text remains in the field; review the card before retrying."],
    improvement_publication_required: ["Опубликуйте новую версию исправления и опишите изменение.", "Publish a newer correction and describe the change."],
    improvement_verification_required: ["Нужен успешный новый тест после отметки исправления, для той же текущей публикации, и ваша оценка результата.", "Choose a successful new test created after marking the correction, for the same current publication, and review its result."],
    improvement_transition_invalid: ["Переход статуса недоступен. Обновите карточку.", "This status transition is unavailable. Refresh the card."],
    not_found: ["Замечание или исходный ответ не найдены либо недоступны.", "The issue or source answer was not found or is unavailable."],
    not_authenticated: ["Сессия завершена. Войдите снова; сохраните введённый текст.", "Your session ended. Save your text and sign in again."],
  };
  return (errors[code] ?? ["Результат запроса не подтверждён. Обновите данные перед повтором; текст остался в поле.", "The result is unconfirmed. Refresh before retrying; your text remains in the field."])[ru ? 0 : 1];
}
export function eligibleVerification(session: { publication_version: number; created_at: string }, version: number | null, fixedAt: string | null): boolean {
  return version !== null && !!fixedAt && session.publication_version === version && Date.parse(session.created_at) >= Date.parse(fixedAt);
}
/** An in-flight poll must not undo a newer acknowledged transition or publication check. */
export function newerIssue<T extends { id: string; version: number; current_publication_version: number | null }>(previous: T | null, incoming: T): T {
  if (previous?.id !== incoming.id) return incoming;
  if (previous.version > incoming.version) return previous;
  if (previous.version === incoming.version && previous.current_publication_version !== null
      && incoming.current_publication_version !== null && previous.current_publication_version > incoming.current_publication_version) return previous;
  return incoming;
}
