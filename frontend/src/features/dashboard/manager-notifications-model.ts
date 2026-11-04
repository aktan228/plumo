import type { ManagerNotifications, ManagerStatus } from "@/lib/api/types";

type Locale = "ru" | "en";

const labels: Record<Locale, Record<ManagerStatus, string>> = {
  ru: { not_configured: "Не настроено", waiting_code: "Ждём код от менеджера", awaiting_confirmation: "Ожидает подтверждения", ready: "Готово", needs_attention: "Требует внимания" },
  en: { not_configured: "Not set up", waiting_code: "Waiting for the manager's code", awaiting_confirmation: "Awaiting confirmation", ready: "Ready", needs_attention: "Needs attention" },
};

export function managerStatusLabel(status: ManagerStatus, locale: Locale): string {
  return labels[locale][status];
}

export function managerStatusTone(status: ManagerStatus): "ok" | "warn" | "error" | "idle" {
  if (status === "ready") return "ok";
  if (status === "waiting_code" || status === "awaiting_confirmation") return "warn";
  if (status === "needs_attention") return "error";
  return "idle";
}

const explanations: Record<Locale, Record<ManagerStatus, string>> = {
  ru: {
    not_configured: "Внешнее уведомление не настроено: о передаче диалога менеджер узнает только из кабинета.",
    waiting_code: "Отправьте ссылку менеджеру. Он откроет бота и нажмёт «Запустить». Код действует 15 минут.",
    awaiting_confirmation: "Бот получил код. Проверьте, что это ваш менеджер, и подтвердите чат.",
    ready: "Уведомления о передаче диалога приходят менеджеру в Telegram.",
    needs_attention: "Telegram не доставил последнее уведомление: менеджер заблокировал бота или удалил чат. Попросите его открыть бота снова или привяжите другой чат.",
  },
  en: {
    not_configured: "External notification is not set up: the manager will see handoffs only in the dashboard.",
    waiting_code: "Send the link to the manager. They open the bot and press Start. The code is valid for 15 minutes.",
    awaiting_confirmation: "The bot received the code. Check that it is your manager and confirm the chat.",
    ready: "Handoff notifications reach the manager in Telegram.",
    needs_attention: "Telegram did not deliver the last notification: the manager blocked the bot or deleted the chat. Ask them to open the bot again or bind another chat.",
  },
};

export function managerExplanation(state: ManagerNotifications, locale: Locale): string {
  return explanations[locale][state.status];
}

/** A change of manager is in progress: someone is confirmed and another chat waits for confirmation. */
export function isChangingManager(state: ManagerNotifications): boolean {
  return state.recipient !== null && state.candidate !== null;
}
