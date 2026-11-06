// Pure helpers for the Conversations view. Server data in, display values out; no demo data.
import type { DeliveryStatus, DialogItem, DialogList, DialogMessage, DialogMode, ReplyState } from "@/lib/api/types";

export type Locale = "ru" | "en";
export const TIME_ZONE = "Asia/Bishkek";

const channelNames: Record<string, string> = { telegram: "Telegram", instagram: "Instagram", whatsapp: "WhatsApp", voice: "Телефон", cli: "CLI" };
export function channelName(channel: string): string {
  return channelNames[channel] ?? channel;
}

/** What the channel tells us about the customer, never an invented name. */
export function customerName(customer: DialogItem["customer"], channel: string, locale: Locale): string {
  return customer.name || customer.handle || customer.phone || (locale === "ru" ? `Клиент ${channelName(channel)}` : `${channelName(channel)} customer`);
}

export function initials(name: string): string {
  const letters = name.replace(/^@/, "").split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]?.toLocaleUpperCase() ?? "");
  return letters.join("") || "?";
}

/** UTC from the server shown in Bishkek time; a date is added when it is not today there. */
export function formatTime(iso: string, locale: Locale, now: Date = new Date()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const tag = locale === "ru" ? "ru-RU" : "en-GB";
  const day = (value: Date) => value.toLocaleDateString("en-CA", { timeZone: TIME_ZONE });
  const time = date.toLocaleTimeString(tag, { hour: "2-digit", minute: "2-digit", timeZone: TIME_ZONE });
  if (day(date) === day(now)) return time;
  return `${date.toLocaleDateString(tag, { day: "numeric", month: "short", timeZone: TIME_ZONE })}, ${time}`;
}

/** Server pages merged by id, ordered as the server orders them: time, then insertion. */
export function mergeMessages(current: DialogMessage[], incoming: DialogMessage[]): DialogMessage[] {
  const byId = new Map(current.map(item => [item.id, item]));
  for (const item of incoming) byId.set(item.id, item);
  return [...byId.values()].sort((a, b) => {
    const time = new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
    return time !== 0 ? time : (a.seq ?? 0) - (b.seq ?? 0);
  });
}

const deliveryLabels: Record<Locale, Record<DeliveryStatus, string>> = {
  ru: { queued: "В очереди", sending: "Отправляется", sent: "Принято каналом", failed: "Не отправлено", unknown: "Статус неизвестен", cancelled: "Отменено" },
  en: { queued: "Queued", sending: "Sending", sent: "Accepted by channel", failed: "Not sent", unknown: "Status unknown", cancelled: "Cancelled" },
};
export function deliveryLabel(status: DeliveryStatus, locale: Locale): string {
  return deliveryLabels[locale][status];
}

const deliveryReasons: Record<Locale, Record<string, string>> = {
  ru: {
    mode_changed: "режим диалога изменился до отправки", agent_disabled: "автоответы выключены", channel_disconnected: "канал отключён",
    channel_action_required: "канал требует действия", window_closed: "окно ответа Instagram закрыто", recipient_blocked: "клиент заблокировал бота",
    token_invalid: "токен канала недействителен", retries_exhausted: "канал не ответил после повторов", interrupted: "отправка прервалась",
    telegram_timeout: "Telegram не ответил вовремя", instagram_timeout: "Instagram не ответил вовремя",
    credential_missing: "серверная конфигурация канала недоступна", credential_empty: "в серверной конфигурации нет токена",
    missing_permission: "у приложения нет прав на отправку", recipient_unavailable: "клиент недоступен в Instagram",
    chat_not_found: "чат не найден", no_reply_target: "неизвестно, куда отвечать", conversation_missing: "диалог не найден",
    worker_crashed: "обработчик остановился", marked_failed: "отмечено как недоставленное", confirmed_by_operator: "подтверждено менеджером",
  },
  en: {
    mode_changed: "the dialog mode changed before sending", agent_disabled: "automatic replies are off", channel_disconnected: "the channel is disconnected",
    channel_action_required: "the channel needs attention", window_closed: "the Instagram reply window is closed", recipient_blocked: "the customer blocked the bot",
    token_invalid: "the channel token is invalid", retries_exhausted: "the channel did not respond after retries", interrupted: "sending was interrupted",
    telegram_timeout: "Telegram did not answer in time", instagram_timeout: "Instagram did not answer in time",
    credential_missing: "the channel's server configuration is unavailable", credential_empty: "the server configuration has no token",
    missing_permission: "the app may not send messages", recipient_unavailable: "the customer is unavailable on Instagram",
    chat_not_found: "chat not found", no_reply_target: "no reply address", conversation_missing: "conversation not found",
    worker_crashed: "the worker stopped", marked_failed: "marked as not delivered", confirmed_by_operator: "confirmed by the manager",
  },
};
export function deliveryReason(code: string | null, locale: Locale): string | null {
  if (!code) return null;
  return deliveryReasons[locale][code] ?? code;
}

export function modeLabel(mode: DialogMode, locale: Locale, agentEnabled = true): string {
  const ru = { ai: agentEnabled ? "Отвечает ИИ" : "Автоответы выключены", waiting: "Нужен менеджер", human: "У менеджера" };
  const en = { ai: agentEnabled ? "AI is replying" : "Automatic replies off", waiting: "Needs a manager", human: "With a manager" };
  return (locale === "ru" ? ru : en)[mode];
}

const replyReasons: Record<Locale, Record<string, string>> = {
  ru: {
    take_dialog_first: "Возьмите диалог, чтобы ответить клиенту.", channel_not_connected: "У этого диалога нет подключённого канала для ответа.",
    channel_disconnected: "Канал отключён: отправка невозможна.", channel_action_required: "Канал требует действия в «Интеграциях».",
    window_closed: "Instagram разрешает ответ только в течение 24 часов после последнего сообщения клиента.",
  },
  en: {
    take_dialog_first: "Take the conversation to reply to the customer.", channel_not_connected: "This conversation has no connected channel to reply through.",
    channel_disconnected: "The channel is disconnected; sending is not possible.", channel_action_required: "The channel needs attention in Integrations.",
    window_closed: "Instagram allows a reply only within 24 hours of the customer's last message.",
  },
};
export function replyHint(reply: ReplyState, locale: Locale): string | null {
  if (reply.allowed || !reply.reason) return null;
  return replyReasons[locale][reply.reason] ?? reply.reason;
}

const utf8 = new TextEncoder();
/** Whether the text fits the channel: Telegram counts characters, Instagram counts UTF-8 bytes. */
export function textFits(reply: ReplyState, text: string): boolean {
  if (reply.max_bytes != null) return utf8.encode(text).length <= reply.max_bytes;
  if (reply.max_chars != null) return text.length <= reply.max_chars;
  return true;
}
export function textUsage(reply: ReplyState, text: string): string | null {
  if (reply.max_bytes != null) return `${utf8.encode(text).length}/${reply.max_bytes} B`;
  if (reply.max_chars != null && text.length > reply.max_chars * 0.8) return `${text.length}/${reply.max_chars}`;
  return null;
}

export type PendingSend = { key: string; text: string };
/** An acknowledgement must not erase edits made while the request was in flight. */
export function draftAfterAcceptance(draft: string, submitted: string): string {
  return draft.trim() === submitted ? "" : draft;
}

/** Rebuild the requested window with cursors; the API caps each page at 100. */
export async function loadDialogWindow(count: number, fetchPage: (limit: number, cursor?: string) => Promise<DialogList>): Promise<DialogList> {
  const items = new Map<string, DialogItem>();
  let cursor: string | undefined;
  const seen = new Set<string>();
  do {
    const page = await fetchPage(Math.min(100, count - items.size), cursor);
    for (const item of page.items) items.set(item.id, item);
    if (!page.next_cursor || items.size >= count) return { items: [...items.values()], next_cursor: page.next_cursor };
    if (seen.has(page.next_cursor)) throw new Error("Repeated conversation cursor");
    seen.add(page.next_cursor);
    cursor = page.next_cursor;
  } while (true);
}
/**
 * Recover an unacknowledged operation before sending edited text as a new message.
 * Keep both its key and original body, even when the draft has changed.
 */
export function sendKey(pending: PendingSend | undefined, text: string, makeKey: () => string): PendingSend {
  return pending ?? { key: makeKey(), text };
}

const eventLabels: Record<Locale, Record<string, string>> = {
  ru: { takeover: "Менеджер взял диалог · автоматические ответы приостановлены", resume: "Диалог возвращён агенту" },
  en: { takeover: "Manager took the conversation · automatic replies paused", resume: "Conversation returned to the agent" },
};
export function eventText(message: DialogMessage, locale: Locale): string {
  const label = (message.event && eventLabels[locale][message.event]) || message.text;
  return message.author ? `${label} · ${message.author}` : label;
}

const attachmentNames: Record<Locale, Record<string, string>> = {
  ru: { photo: "фото", image: "фото", voice: "голосовое", audio: "аудио", video: "видео", video_note: "видеосообщение", document: "файл", file: "файл", sticker: "стикер" },
  en: { photo: "photo", image: "photo", voice: "voice message", audio: "audio", video: "video", video_note: "video message", document: "file", file: "file", sticker: "sticker" },
};
export function unsupportedText(kind: string, locale: Locale): string {
  const name = attachmentNames[locale][kind] ?? kind;
  return locale === "ru" ? `Вложение: ${name} — в этой версии не поддерживается` : `Attachment: ${name} — not supported in this version`;
}

/** "Голосовое, 12 с" over a transcript, or "Голосовое, не распознано". */
export function voiceLabel(voice: { duration_s: number | null; transcribed: boolean }, locale: Locale): string {
  const seconds = voice.duration_s != null ? (locale === "ru" ? `, ${voice.duration_s} с` : `, ${voice.duration_s} s`) : "";
  if (!voice.transcribed) return locale === "ru" ? "Голосовое, не распознано" : "Voice message, not recognized";
  return locale === "ru" ? `Голосовое${seconds}` : `Voice message${seconds}`;
}

const conversationId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** The dialog a notification link points at (`/dashboard?conversation=<id>`), or null for anything else. */
export function linkedConversation(value: string | string[] | null | undefined): string | null {
  const id = (Array.isArray(value) ? value[0] : value ?? "").trim().toLowerCase();
  return conversationId.test(id) ? id : null;
}

/** Where the dashboard sends an anonymous visitor: sign in, then back to the same dialog. */
export function dashboardLoginPath(conversation: string | null): string {
  const target = conversation ? `/dashboard?conversation=${conversation}` : "/dashboard";
  return `/login?next=${encodeURIComponent(target)}`;
}

const notificationTexts: Record<Locale, Record<string, string>> = {
  ru: {
    queued: "Уведомление менеджеру в очереди.",
    sending: "Отправляем уведомление менеджеру…",
    sent: "Менеджер уведомлён в Telegram.",
    failed: "Уведомление менеджеру не отправлено.",
    unknown: "Неизвестно, дошло ли уведомление: Telegram не ответил. Уточните у менеджера.",
    cancelled: "Внешнее уведомление не настроено: менеджер видит передачу только в кабинете.",
  },
  en: {
    queued: "Manager notification is queued.",
    sending: "Sending the manager notification…",
    sent: "The manager was notified in Telegram.",
    failed: "The manager notification was not sent.",
    unknown: "Unknown whether the notification arrived: Telegram did not answer. Check with the manager.",
    cancelled: "External notification is not set up: the manager sees the handoff only in the dashboard.",
  },
};

/** What the dashboard says about the manager notification. "Notified" only after Telegram accepted it. */
export function notificationText(status: string | null | undefined, locale: Locale): string | null {
  return status ? notificationTexts[locale][status] ?? null : null;
}

export function notificationTone(status: string | null | undefined): "ok" | "warn" | "error" | "idle" {
  if (status === "sent") return "ok";
  if (status === "failed" || status === "unknown") return "error";
  if (status === "cancelled") return "warn";
  return "idle";
}
