"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import Alert02Icon from "@hugeicons/core-free-icons/Alert02Icon";
import ArrowLeft01Icon from "@hugeicons/core-free-icons/ArrowLeft01Icon";
import Cancel01Icon from "@hugeicons/core-free-icons/Cancel01Icon";
import Loading03Icon from "@hugeicons/core-free-icons/Loading03Icon";
import Refresh01Icon from "@hugeicons/core-free-icons/Refresh01Icon";
import Search01Icon from "@hugeicons/core-free-icons/Search01Icon";
import SentIcon from "@hugeicons/core-free-icons/SentIcon";
import UserIcon from "@hugeicons/core-free-icons/UserIcon";
import { PlumoIcon } from "@/components/ui/plumo-icon";
import { ApiError, api, goToLogin } from "@/lib/api/client";
import type { DialogDetail, DialogItem, DialogList, DialogMessage, DialogMessages, DialogMode, ManagerSend } from "@/lib/api/types";
import { usePolling } from "@/lib/api/use-polling";
import { useLanguage } from "@/lib/i18n";
import { apiErrorText } from "./api-messages";
import {
  channelName, customerName, deliveryLabel, deliveryReason, eventText, formatTime, initials, mergeMessages,
  modeLabel, replyHint, sendKey, textFits, textUsage, unsupportedText, type PendingSend,
} from "./dialogue-model";

const labels = {
  ru: {
    title: "Диалоги", all: "Все каналы", allModes: "Все диалоги", searchLabel: "Поиск по имени, контакту или сообщению", searchPlaceholder: "Поиск диалогов",
    ai: "Отвечает ИИ", waiting: "Нужен менеджер", human: "У менеджера",
    take: "Взять диалог", resume: "Вернуть агенту", profile: "Карточка клиента", back: "К списку", close: "Закрыть карточку",
    empty: "Диалогов не найдено", emptyText: "Попробуйте другой запрос или измените фильтры.", clear: "Сбросить фильтры",
    none: "Пока нет диалогов", noneText: "Подключите Telegram или Instagram в «Интеграциях» и напишите в канал с другого аккаунта.",
    pick: "Выберите диалог слева.", loading: "Загружаем…", more: "Показать ещё", older: "Показать более ранние",
    customer: "Клиент", contact: "Контакт", phone: "Телефон", language: "Язык", channel: "Канал", summary: "Краткое резюме", need: "Потребность", handoff: "Передача менеджеру",
    agent: "Plumo", manager: "Менеджер", reply: "Написать сообщение…", send: "Отправить", replyVia: "Ответ уйдёт в",
    unread: "непрочитанных", messages: "Сообщения", details: "Информация о клиенте",
    offline: "Нет связи с сервером. Показаны последние загруженные данные, повторяем запрос…", retry: "Повторить",
    markSent: "Клиент получил", markFailed: "Не дошло", resend: "Отправить ещё раз", unknownHint: "Проверьте в канале, дошло ли сообщение.",
    tooLong: "Текст длиннее, чем разрешает канал.", waitingHandoff: "Агент запросил менеджера",
    languages: { ru: "Русский", ky: "Кыргызский", mixed: "Смешанный" } as Record<string, string>,
    reasons: { user_requested_human: "клиент просит менеджера", hot_lead: "горячий клиент", ready_for_meeting: "готов к встрече", no_knowledge: "вопрос вне базы знаний", customer_dissatisfied: "клиент недоволен", agent_unclear_twice: "агент дважды не понял", model_unavailable: "модель недоступна", manager_takeover: "менеджер взял диалог" } as Record<string, string>,
  },
  en: {
    title: "Conversations", all: "All channels", allModes: "All conversations", searchLabel: "Search name, contact or message", searchPlaceholder: "Search conversations",
    ai: "AI is replying", waiting: "Needs a manager", human: "With a manager",
    take: "Take conversation", resume: "Return to agent", profile: "Customer details", back: "Back to list", close: "Close customer details",
    empty: "No conversations found", emptyText: "Try a different search or change the filters.", clear: "Reset filters",
    none: "No conversations yet", noneText: "Connect Telegram or Instagram in Integrations and message the channel from another account.",
    pick: "Choose a conversation on the left.", loading: "Loading…", more: "Show more", older: "Show earlier messages",
    customer: "Customer", contact: "Contact", phone: "Phone", language: "Language", channel: "Channel", summary: "Summary", need: "Customer need", handoff: "Manager handoff",
    agent: "Plumo", manager: "Manager", reply: "Write a message…", send: "Send", replyVia: "Reply goes to",
    unread: "unread", messages: "Messages", details: "Customer information",
    offline: "No connection to the server. Showing the last loaded data, retrying…", retry: "Retry",
    markSent: "Customer got it", markFailed: "Did not arrive", resend: "Send again", unknownHint: "Check in the channel whether the message arrived.",
    tooLong: "The text is longer than the channel allows.", waitingHandoff: "The agent asked for a manager",
    languages: { ru: "Russian", ky: "Kyrgyz", mixed: "Mixed" } as Record<string, string>,
    reasons: { user_requested_human: "customer asks for a manager", hot_lead: "hot lead", ready_for_meeting: "ready to meet", no_knowledge: "question outside the knowledge base", customer_dissatisfied: "customer is unhappy", agent_unclear_twice: "agent did not understand twice", model_unavailable: "model unavailable", manager_takeover: "manager took the conversation" } as Record<string, string>,
  },
};

const button = "cursor-pointer rounded-lg border border-solid border-plumo-line bg-white px-3 py-2 font-[inherit] text-xs font-medium text-plumo-ink transition-colors hover:bg-plumo-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-not-allowed disabled:opacity-60";
const iconButton = "flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-plumo-muted hover:bg-plumo-soft hover:text-plumo-blue focus-visible:outline-2 focus-visible:outline-plumo-blue";
const channelColors: Record<string, string> = { whatsapp: "bg-emerald-50 text-emerald-700", telegram: "bg-sky-50 text-sky-700", instagram: "bg-fuchsia-50 text-fuchsia-700" };
const deliveryColors = { queued: "text-plumo-muted", sending: "text-plumo-muted", sent: "text-emerald-700", failed: "text-red-700", unknown: "text-amber-700", cancelled: "text-plumo-muted" };
const PAGE = 30;

function ChannelBadge({ channel }: { channel: string }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] font-medium ${channelColors[channel] ?? "bg-plumo-line/60 text-plumo-muted"}`}><span className="size-1.5 rounded-full bg-current" />{channelName(channel)}</span>;
}

export function Dialogues({ active }: { active: boolean }) {
  const { locale } = useLanguage();
  const c = labels[locale];
  const [items, setItems] = useState<DialogItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [listState, setListState] = useState<"loading" | "ready" | "offline">("loading");
  const [channel, setChannel] = useState("all");
  const [mode, setMode] = useState<DialogMode | "all">("all");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [pageLimit, setPageLimit] = useState(PAGE);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DialogDetail | null>(null);
  const [older, setOlder] = useState<{ messages: DialogMessage[]; cursor: string | null }>({ messages: [], cursor: null });
  const [detailError, setDetailError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<Record<string, PendingSend>>({});
  const [sendErrors, setSendErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [mobileChat, setMobileChat] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  const readSent = useRef<Record<string, number>>({});
  const selectedRef = useRef<string | null>(null);
  // Declared before the pollers: they read the selected id when a request starts.
  useEffect(() => { selectedRef.current = selectedId; }, [selectedId]);

  // Search runs on the server; wait for a pause in typing.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const filters = { channel: channel === "all" ? undefined : channel, mode: mode === "all" ? undefined : mode, q: query || undefined };
  const listKey = `${filters.channel}|${filters.mode}|${filters.q}|${pageLimit}`;

  const loadList = useCallback(async (signal: AbortSignal) => {
    try {
      const data = await api<DialogList>("conversations", { query: { ...filters, limit: Math.min(pageLimit, 100) }, signal });
      setItems(data.items);
      setNextCursor(data.next_cursor);
      setListState("ready");
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.unauthenticated) goToLogin();
        setListState(state => state === "loading" && !error.unavailable ? "ready" : "offline");
      }
      throw error;
    }
  }, [listKey]); // listKey carries the filters and the page size
  const refreshList = usePolling(loadList, 4_000, listKey, active);

  const loadDetail = useCallback(async (signal: AbortSignal) => {
    const id = selectedRef.current;
    if (!id) return;
    try {
      const data = await api<DialogDetail>(`conversations/${id}`, { signal });
      if (selectedRef.current !== id) return;
      setDetail(data);
      setDetailError(null);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.unauthenticated) goToLogin();
        if (selectedRef.current === id) setDetailError(apiErrorText(error.code, locale, error.message));
      }
      throw error;
    }
  }, [locale]);
  const refreshDetail = usePolling(loadDetail, 3_000, selectedId ?? "none", active && selectedId !== null);

  const current = detail && detail.dialog.id === selectedId ? detail : null;
  const messages = current ? mergeMessages(older.messages, current.messages) : [];
  const newestSeq = messages.reduce((max, item) => Math.max(max, item.seq ?? 0), 0);

  // The operator saw the dialog: move the server read cursor (never the channel's read receipt).
  useEffect(() => {
    if (!current || !active || current.dialog.unread === 0 || newestSeq === 0 || document.hidden) return;
    if (!mobileChat && typeof window !== "undefined" && window.matchMedia("(max-width: 767px)").matches) return;
    if ((readSent.current[current.dialog.id] ?? 0) >= newestSeq) return;
    readSent.current[current.dialog.id] = newestSeq;
    api(`conversations/${current.dialog.id}/read`, { method: "POST", body: { seq: newestSeq } }).then(() => refreshList(), () => { readSent.current[current.dialog.id] = 0; });
  }, [current, newestSeq, active, mobileChat, refreshList]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest", behavior: "instant" });
  }, [selectedId, current?.messages.length, mobileChat]);

  function openConversation(item: DialogItem) {
    if (item.id !== selectedId) {
      setDetail(null);
      setOlder({ messages: [], cursor: null });
      setDetailError(null);
    }
    setSelectedId(item.id);
    setMobileChat(true);
    setDetailsOpen(false);
    requestAnimationFrame(() => backRef.current?.focus());
  }

  async function action(key: string, run: () => Promise<unknown>) {
    if (!current) return;
    const id = current.dialog.id;
    setBusy(key);
    setSendErrors(values => ({ ...values, [id]: "" }));
    try {
      await run();
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.unauthenticated) goToLogin();
        setSendErrors(values => ({ ...values, [id]: apiErrorText(error.code, locale, error.message) }));
      }
    } finally {
      setBusy(null);
      refreshDetail();
      refreshList();
    }
  }

  function changeMode(next: "takeover" | "resume") {
    if (!current) return;
    void action(next, () => api(`conversations/${current.dialog.id}/${next}`, { method: "POST" }));
  }

  async function loadOlder() {
    if (!current) return;
    const cursor = older.cursor ?? current.older_cursor;
    if (!cursor) return;
    const id = current.dialog.id;
    try {
      const page = await api<DialogMessages>(`conversations/${id}/messages`, { query: { before: cursor } });
      if (selectedRef.current !== id) return;
      setOlder(value => ({ messages: mergeMessages(value.messages, page.messages), cursor: page.older_cursor ?? "" }));
    } catch (error) {
      if (error instanceof ApiError) setDetailError(apiErrorText(error.code, locale, error.message));
    }
  }

  async function loadMore() {
    if (!nextCursor) return;
    try {
      const page = await api<DialogList>("conversations", { query: { ...filters, limit: PAGE, cursor: nextCursor } });
      setItems(value => [...value, ...page.items.filter(item => !value.some(known => known.id === item.id))]);
      setNextCursor(page.next_cursor);
      setPageLimit(value => value + PAGE);
    } catch {
      setListState("offline");
    }
  }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!current || busy) return;
    const id = current.dialog.id;
    const text = (drafts[id] ?? "").trim();
    if (!text || !current.reply.allowed) return;
    if (!textFits(current.reply, text)) {
      setSendErrors(values => ({ ...values, [id]: c.tooLong }));
      return;
    }
    const attempt = sendKey(pending[id], text, () => crypto.randomUUID());
    setPending(values => ({ ...values, [id]: attempt }));
    setBusy("send");
    setSendErrors(values => ({ ...values, [id]: "" }));
    try {
      const result = await api<ManagerSend>(`conversations/${id}/messages`, { method: "POST", body: { text, idempotency_key: attempt.key } });
      // Accepted by the server: the text now belongs to one delivery operation.
      setDrafts(values => ({ ...values, [id]: "" }));
      setPending(values => { const next = { ...values }; delete next[id]; return next; });
      setDetail(value => value && value.dialog.id === id ? { ...value, messages: mergeMessages(value.messages, [result.message]) } : value);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.unauthenticated) goToLogin();
        setSendErrors(values => ({ ...values, [id]: apiErrorText(error.code, locale, error.message) }));
      }
    } finally {
      setBusy(null);
      refreshDetail();
      refreshList();
    }
  }

  const name = (item: DialogItem) => customerName(item.customer, item.channel, locale);
  const agentEnabled = current?.connection?.agent_enabled ?? true;
  const draft = selectedId ? drafts[selectedId] ?? "" : "";
  const sendError = selectedId ? sendErrors[selectedId] : "";
  const filtered = channel !== "all" || mode !== "all" || query !== "";
  const waitingCount = items.filter(item => item.mode === "waiting").length;

  function bubble(message: DialogMessage, dialog: DialogItem) {
    if (message.role === "system") {
      return <p key={message.id} className="mx-auto my-1 max-w-[90%] rounded-lg bg-plumo-line/60 px-3 py-2 text-center text-[10px] leading-5 text-plumo-muted">{eventText(message, locale)} · {formatTime(message.timestamp, locale)}</p>;
    }
    const mine = message.role !== "user";
    const author = message.role === "user" ? name(dialog) : message.role === "assistant" ? c.agent : message.author ? `${c.manager} · ${message.author}` : c.manager;
    const delivery = message.delivery;
    return <div key={message.id} className={`flex max-w-[88%] flex-col sm:max-w-[80%] ${mine ? "self-end" : "self-start"}`}>
      <span className={`mb-1.5 text-[10px] text-plumo-muted ${mine ? "text-right" : ""}`}>{author}</span>
      <div className={`rounded-2xl px-4 py-3 ${mine ? "rounded-tr-sm bg-plumo-soft" : "rounded-tl-sm border border-solid border-plumo-line bg-white"} ${delivery && (delivery.status === "cancelled" || delivery.status === "failed") ? "opacity-70" : ""}`}>
        {message.unsupported ? <p className="m-0 text-[13px] italic leading-[1.65] text-plumo-muted">{unsupportedText(message.unsupported, locale)}</p>
          : <p className="m-0 whitespace-pre-wrap break-words text-[13px] leading-[1.65] [overflow-wrap:anywhere]">{message.text}</p>}
        <p className="mb-0 mt-1.5 text-right text-[10px] text-plumo-muted">{formatTime(message.timestamp, locale)}</p>
      </div>
      {delivery && <div className={`mt-1 text-right text-[10px] ${deliveryColors[delivery.status]}`}>
        <span>{deliveryLabel(delivery.status, locale)}{deliveryReason(delivery.error_code, locale) && delivery.status !== "sent" ? ` · ${deliveryReason(delivery.error_code, locale)}` : ""}</span>
        {(delivery.status === "unknown" || (delivery.status === "failed" && message.role === "manager")) && <div className="mt-1.5 flex flex-wrap justify-end gap-1.5">
          {delivery.status === "unknown" && <span className="w-full text-plumo-muted">{c.unknownHint}</span>}
          {delivery.status === "unknown" && <button type="button" className={button} disabled={busy !== null} onClick={() => action(`resolve:${delivery.id}`, () => api(`outbound-messages/${delivery.id}/resolve`, { method: "POST", body: { action: "mark_sent" } }))}>{c.markSent}</button>}
          {delivery.status === "unknown" && <button type="button" className={button} disabled={busy !== null} onClick={() => action(`resolve:${delivery.id}`, () => api(`outbound-messages/${delivery.id}/resolve`, { method: "POST", body: { action: "mark_failed" } }))}>{c.markFailed}</button>}
          {message.role === "manager" && <button type="button" className={button} disabled={busy !== null || !current?.reply.allowed} onClick={() => action(`resolve:${delivery.id}`, () => api(`outbound-messages/${delivery.id}/resolve`, { method: "POST", body: { action: "retry" } }))}>{c.resend}</button>}
        </div>}
      </div>}
    </div>;
  }

  function customerDetails(value: DialogDetail) {
    const dialog = value.dialog;
    const language = c.languages[value.customer.language];
    const rows: [string, string][] = [];
    if (dialog.customer.handle) rows.push([c.contact, dialog.customer.handle]);
    if (dialog.customer.phone) rows.push([c.phone, dialog.customer.phone]);
    if (language) rows.push([c.language, language]);
    if (value.connection) rows.push([c.channel, `${channelName(value.connection.channel)} · ${value.connection.account.username ? `@${value.connection.account.username}` : value.connection.account.display_name}`]);
    if (value.summary?.summary) rows.push([c.summary, value.summary.summary]);
    const need = value.summary?.need || value.customer.need;
    if (need) rows.push([c.need, need]);
    return <>
      <div className="flex items-center justify-between"><h2 className="m-0 text-sm font-semibold">{c.customer}</h2><button type="button" aria-label={c.close} onClick={() => setDetailsOpen(false)} className={`${iconButton} xl:hidden`}><PlumoIcon icon={Cancel01Icon} size={18} /></button></div>
      <div className="mt-6 flex items-center gap-3"><span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-plumo-soft text-sm font-semibold text-plumo-blue">{initials(name(dialog))}</span><div><p className="m-0 text-sm font-semibold">{name(dialog)}</p><p className="mb-0 mt-1 text-xs text-plumo-muted">{channelName(dialog.channel)}</p></div></div>
      <dl className="mb-0 mt-6 space-y-5">{rows.map(([label, text]) => <div key={label}><dt className="text-xs text-plumo-muted">{label}</dt><dd className="mb-0 ml-0 mt-1.5 break-words text-[13px] leading-6">{text}</dd></div>)}</dl>
      {value.handoff && <div className="mt-6 rounded-xl bg-plumo-soft p-4"><h3 className="m-0 text-xs font-semibold text-plumo-blue">{c.handoff}</h3><p className="mb-0 mt-2 text-[13px] leading-6">{c.reasons[value.handoff.reason] ?? value.handoff.reason}</p></div>}
    </>;
  }

  return <div className="flex h-full min-h-0 flex-col">
    <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 px-5 py-4 sm:px-6">
      <div className="flex items-center gap-3"><h1 className="m-0 text-xl font-semibold tracking-tight">{c.title}</h1><span className="rounded-md bg-plumo-line/60 px-2 py-1 text-xs text-plumo-muted">{items.length}{nextCursor ? "+" : ""}</span></div>
      <span className="flex items-center gap-2 text-xs text-plumo-muted"><span className="size-1.5 rounded-full bg-amber-500" />{c.waiting}: {waitingCount}</span>
    </div>
    {listState === "offline" && <div role="alert" className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-0 border-t border-solid border-amber-200 bg-amber-50 px-5 py-2 text-xs text-amber-800"><span className="flex items-center gap-2"><PlumoIcon icon={Alert02Icon} size={16} />{c.offline}</span><button type="button" className={button} onClick={() => { refreshList(); refreshDetail(); }}><PlumoIcon icon={Refresh01Icon} size={14} />{c.retry}</button></div>}
    <div className="relative flex min-h-0 flex-1 overflow-hidden border-0 border-t border-solid border-plumo-line bg-white">
      <section aria-label={c.allModes} className={`${mobileChat ? "hidden" : "flex"} w-full shrink-0 flex-col border-0 border-r border-solid border-plumo-line md:flex md:w-[290px] 2xl:w-[330px]`}>
        <div className="space-y-3 p-4">
          <label className="relative block"><span className="pointer-events-none absolute left-3 top-3 text-plumo-muted"><PlumoIcon icon={Search01Icon} size={16} /></span><input type="search" aria-label={c.searchLabel} placeholder={c.searchPlaceholder} value={search} maxLength={100} onChange={event => setSearch(event.target.value)} className="h-10 w-full rounded-lg border border-solid border-plumo-line bg-plumo-line/20 pl-9 pr-3 font-[inherit] text-xs text-plumo-ink focus:outline-2 focus:outline-plumo-blue" /></label>
          <div className="flex gap-2">
            <select aria-label={c.all} value={channel} onChange={event => setChannel(event.target.value)} className="min-w-0 flex-1 rounded-lg border border-solid border-plumo-line bg-white px-2 py-2 font-[inherit] text-xs text-plumo-ink focus:outline-plumo-blue"><option value="all">{c.all}</option>{["telegram", "instagram", "whatsapp"].map(value => <option key={value} value={value}>{channelName(value)}</option>)}</select>
            <select aria-label={c.allModes} value={mode} onChange={event => setMode(event.target.value as DialogMode | "all")} className="min-w-0 flex-1 rounded-lg border border-solid border-plumo-line bg-white px-2 py-2 font-[inherit] text-xs text-plumo-ink focus:outline-plumo-blue"><option value="all">{c.allModes}</option>{(["waiting", "ai", "human"] as const).map(value => <option key={value} value={value}>{c[value]}</option>)}</select>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2" aria-busy={listState === "loading"}>
          {listState === "loading" && <p role="status" className="flex items-center justify-center gap-2 py-10 text-xs text-plumo-muted"><PlumoIcon icon={Loading03Icon} size={16} className="animate-spin" />{c.loading}</p>}
          {items.map(item => <button key={item.id} type="button" aria-current={selectedId === item.id ? "true" : undefined} onClick={() => openConversation(item)} className={`mb-1 block w-full cursor-pointer rounded-xl border-0 p-3 text-left font-[inherit] transition-colors focus-visible:outline-2 focus-visible:outline-plumo-blue ${selectedId === item.id ? "bg-plumo-soft" : "bg-white hover:bg-plumo-line/30"}`}>
            <div className="flex items-center gap-2.5"><span className={`flex size-9 shrink-0 items-center justify-center rounded-xl text-xs font-medium ${selectedId === item.id ? "bg-white text-plumo-blue" : "bg-plumo-line/60 text-plumo-muted"}`}>{initials(name(item))}</span><span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-plumo-ink">{name(item)}</span><span className="text-[10px] text-plumo-muted">{formatTime(item.activity_at, locale)}</span></div>
            <p className="mb-2 mt-2 truncate text-xs leading-5 text-plumo-muted">{item.last_message?.text ?? "—"}</p>
            <div className="flex items-center justify-between gap-2"><ChannelBadge channel={item.channel} /><span className="flex items-center gap-1.5 text-[10px] text-plumo-muted">{c[item.mode]}{item.unread > 0 && <span aria-label={`${item.unread} ${c.unread}`} className="flex h-4 min-w-4 items-center justify-center rounded-full bg-plumo-blue px-1 text-[9px] text-white">{item.unread}</span>}</span></div>
          </button>)}
          {nextCursor && <button type="button" className={`${button} mx-auto mt-2 block`} onClick={loadMore}>{c.more}</button>}
          {listState === "ready" && items.length === 0 && (filtered
            ? <div className="px-4 py-12 text-center"><PlumoIcon icon={Search01Icon} /><h2 className="mb-0 mt-3 text-sm font-medium">{c.empty}</h2><p className="text-xs leading-5 text-plumo-muted">{c.emptyText}</p><button type="button" className={button} onClick={() => { setChannel("all"); setMode("all"); setSearch(""); }}>{c.clear}</button></div>
            : <div className="px-4 py-12 text-center"><h2 className="m-0 text-sm font-medium">{c.none}</h2><p className="mb-0 mt-2 text-xs leading-5 text-plumo-muted">{c.noneText}</p></div>)}
        </div>
      </section>
      <section aria-label={c.messages} className={`${mobileChat ? "flex" : "hidden"} min-w-0 flex-1 flex-col md:flex`}>
        {!selectedId ? <div className="flex flex-1 items-center justify-center p-8 text-center text-sm text-plumo-muted">{c.pick}</div>
          : !current ? <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center text-sm text-plumo-muted">
            {detailError ? <><span className="text-red-700">{detailError}</span><button type="button" className={button} onClick={refreshDetail}>{c.retry}</button></> : <span className="flex items-center gap-2"><PlumoIcon icon={Loading03Icon} size={16} className="animate-spin" />{c.loading}</span>}
            <button type="button" className={`${button} md:hidden`} onClick={() => setMobileChat(false)}>{c.back}</button>
          </div>
          : <>
            <div className="flex min-h-[78px] shrink-0 flex-wrap items-center justify-between gap-2 border-0 border-b border-solid border-plumo-line px-4 py-3 sm:px-5">
              <div className="flex min-w-0 items-center gap-2"><button ref={backRef} type="button" aria-label={c.back} className={`${iconButton} md:hidden`} onClick={() => { setMobileChat(false); setDetailsOpen(false); }}><PlumoIcon icon={ArrowLeft01Icon} size={18} /></button><div className="min-w-0"><h2 className="m-0 truncate text-sm font-semibold">{name(current.dialog)}</h2><div className="mt-1 flex items-center gap-2 text-[10px] text-plumo-muted"><span>{channelName(current.dialog.channel)}</span><span>·</span><span role="status">{modeLabel(current.dialog.mode, locale, agentEnabled)}</span></div></div></div>
              <div className="flex items-center gap-1.5">
                <button type="button" disabled={busy !== null} className={`flex cursor-pointer items-center gap-1.5 rounded-lg border border-solid px-3 py-2 font-[inherit] text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-wait disabled:opacity-70 ${current.dialog.mode !== "human" ? "border-plumo-blue bg-plumo-blue text-white hover:bg-plumo-blue/90" : "border-plumo-line bg-white text-plumo-ink hover:bg-plumo-soft"}`} onClick={() => changeMode(current.dialog.mode === "human" ? "resume" : "takeover")}>
                  {(busy === "takeover" || busy === "resume") && <PlumoIcon icon={Loading03Icon} size={14} className="animate-spin" />}{current.dialog.mode === "human" ? c.resume : c.take}
                </button>
                <button type="button" aria-label={c.profile} aria-expanded={detailsOpen} aria-controls="customer-details" className={`${iconButton} xl:hidden`} onClick={() => setDetailsOpen(value => !value)}><PlumoIcon icon={UserIcon} size={18} /></button>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto bg-plumo-line/15 px-4 py-5 sm:px-6">
              {(older.cursor ?? current.older_cursor) && <p className="mb-4 mt-0 text-center"><button type="button" className={button} onClick={loadOlder}>{c.older}</button></p>}
              {current.dialog.mode === "waiting" && <p className="mx-auto mb-4 mt-0 max-w-[90%] rounded-lg bg-amber-50 px-3 py-2 text-center text-[11px] text-amber-800">{c.waitingHandoff}{current.handoff ? `: ${c.reasons[current.handoff.reason] ?? current.handoff.reason}` : ""}</p>}
              <div className="flex flex-col gap-4">{messages.map(message => bubble(message, current.dialog))}</div><div ref={endRef} />
            </div>
            <form onSubmit={send} className="shrink-0 border-0 border-t border-solid border-plumo-line bg-white p-4">
              <p id="composer-hint" className="mb-2 mt-0 text-[11px] text-plumo-muted">{replyHint(current.reply, locale) ?? `${c.replyVia} ${channelName(current.dialog.channel)}${current.reply.window_expires_at ? ` · ${locale === "ru" ? "окно до" : "window until"} ${formatTime(current.reply.window_expires_at, locale)}` : ""}`}</p>
              <div className="flex items-end gap-2 rounded-xl border border-solid border-plumo-line p-2 focus-within:border-plumo-blue">
                <textarea aria-label={c.reply} aria-describedby="composer-hint" placeholder={c.reply} value={draft} rows={2} disabled={!current.reply.allowed}
                  onChange={event => { const value = event.target.value; setDrafts(values => ({ ...values, [current.dialog.id]: value })); }}
                  onKeyDown={event => { if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) event.currentTarget.form?.requestSubmit(); }}
                  className="min-w-0 flex-1 resize-none border-0 bg-transparent p-1.5 font-[inherit] text-[13px] leading-5 text-plumo-ink outline-none disabled:cursor-not-allowed disabled:opacity-50" />
                <button type="submit" aria-label={c.send} title={c.send} disabled={!current.reply.allowed || !draft.trim() || busy !== null} className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg border-0 bg-plumo-blue text-white hover:bg-plumo-blue/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-not-allowed disabled:bg-plumo-line disabled:text-plumo-muted">{busy === "send" ? <PlumoIcon icon={Loading03Icon} size={17} className="animate-spin" /> : <PlumoIcon icon={SentIcon} size={17} />}</button>
              </div>
              <div className="mt-1.5 flex justify-between gap-2 text-[11px]"><span role="alert" className="text-red-700">{sendError}</span><span className={textFits(current.reply, draft) ? "text-plumo-muted" : "text-red-700"}>{textUsage(current.reply, draft)}</span></div>
            </form>
          </>}
      </section>
      {current && <aside id="customer-details" aria-label={c.details} className={`${detailsOpen ? "absolute inset-y-0 right-0 z-10 block w-full max-w-[300px] shadow-xl" : "hidden"} overflow-y-auto border-0 border-l border-solid border-plumo-line bg-white p-5 xl:static xl:block xl:w-[264px] xl:shrink-0 xl:shadow-none`} onKeyDown={event => { if (event.key === "Escape") setDetailsOpen(false); }}>{customerDetails(current)}</aside>}
    </div>
  </div>;
}
