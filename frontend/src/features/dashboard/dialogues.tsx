"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLanguage } from "@/lib/i18n";
import { DashboardIcon } from "./dashboard-icon";
import { exampleConversations, updateConversations, type Channel, type Mode, type Conversation } from "./dialogue-model";

const labels = {
  ru: {
    all: "Все каналы", search: "Поиск по имени, контакту или сообщению", allModes: "Все диалоги",
    ai: "Отвечает ИИ", waiting: "Нужен менеджер", human: "У менеджера", today: "История диалога",
    take: "Взять диалог", resume: "Вернуть агенту", profile: "Карточка клиента", back: "К списку",
    empty: "Диалогов не найдено", emptyText: "Попробуйте другой запрос или измените фильтры.", clear: "Сбросить фильтры",
    customer: "Клиент", summary: "Краткое резюме", need: "Потребность", next: "Следующий шаг", language: "Язык", contact: "Контакт",
    agent: "Plumo", manager: "Менеджер", reply: "Написать сообщение…", send: "Отправить", sendingTo: "Ответ в",
    locked: "Возьмите диалог, чтобы ответить клиенту.", local: "Пример на вымышленных данных. Сообщения в каналы не отправляются.",
    takeEvent: "Менеджер взял диалог · автоматические ответы приостановлены", resumeEvent: "Диалог возвращён агенту",
    unread: "непрочитанных", messages: "Сообщения", details: "Информация о клиенте", close: "Закрыть карточку",
  },
  en: {
    all: "All channels", search: "Search name, contact or message", allModes: "All conversations",
    ai: "AI is replying", waiting: "Needs a manager", human: "With a manager", today: "Conversation history",
    take: "Take conversation", resume: "Return to agent", profile: "Customer details", back: "Back to list",
    empty: "No conversations found", emptyText: "Try a different search or change the filters.", clear: "Reset filters",
    customer: "Customer", summary: "Summary", need: "Customer need", next: "Next step", language: "Language", contact: "Contact",
    agent: "Plumo", manager: "Manager", reply: "Write a message…", send: "Send", sendingTo: "Reply via",
    locked: "Take the conversation to reply to the customer.", local: "Fictional example data. Messages are not sent to channels.",
    takeEvent: "Manager took the conversation · automatic replies paused", resumeEvent: "Conversation returned to the agent",
    unread: "unread", messages: "Messages", details: "Customer information", close: "Close customer details",
  },
};

const button = "cursor-pointer rounded-lg border border-solid border-plumo-line bg-white px-3 py-2 font-[inherit] text-xs font-medium text-plumo-ink transition-colors hover:bg-plumo-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue";
const iconButton = "flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-plumo-muted hover:bg-plumo-soft hover:text-plumo-blue focus-visible:outline-2 focus-visible:outline-plumo-blue";
const channelColors: Record<Channel, string> = { WhatsApp: "bg-emerald-50 text-emerald-700", Telegram: "bg-sky-50 text-sky-700", Instagram: "bg-fuchsia-50 text-fuchsia-700" };

function ChannelBadge({ channel }: { channel: Channel }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] font-medium ${channelColors[channel]}`}><span className="size-1.5 rounded-full bg-current" />{channel}</span>;
}

export function Dialogues() {
  const { locale } = useLanguage();
  const c = labels[locale];
  // Keep Russian customer content when switching the UI language.
  const [conversations, setConversations] = useState(() => exampleConversations(false));
  const [selectedId, setSelectedId] = useState("aibek-wa");
  const [channel, setChannel] = useState<Channel | "all">("all");
  const [mode, setMode] = useState<Mode | "all">("all");
  const [search, setSearch] = useState("");
  const [mobileChat, setMobileChat] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const endRef = useRef<HTMLDivElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  const query = search.trim().toLocaleLowerCase();
  const visible = conversations.filter(item => (channel === "all" || item.channel === channel) && (mode === "all" || item.mode === mode) && (!query || [item.name, item.contact, ...item.messages.map(message => message.text)].some(value => value.toLocaleLowerCase().includes(query))));
  // Keep a selected conversation open even when its status changes during handoff.
  const selected = conversations.find(item => item.id === selectedId)!;
  const draft = drafts[selected.id] ?? "";
  const waitingCount = conversations.filter(item => item.mode === "waiting").length;

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest", behavior: "instant" });
  }, [selected.id, selected.messages.length, mobileChat]);

  function openConversation(item: Conversation) {
    setSelectedId(item.id);
    setMobileChat(true);
    setDetailsOpen(false);
    setConversations(items => updateConversations(items, { type: "read", id: item.id }));
    requestAnimationFrame(() => backRef.current?.focus());
  }

  function changeMode(nextMode: "ai" | "human") {
    setConversations(items => updateConversations(items, {
      type: "mode", id: selected.id, mode: nextMode,
      event: { id: crypto.randomUUID(), role: "event", text: nextMode === "human" ? c.takeEvent : c.resumeEvent, time: new Date().toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Bishkek" }) },
    }));
  }

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selected.mode !== "human" || !draft.trim()) return;
    const id = selected.id;
    setConversations(items => updateConversations(items, { type: "send", id, message: {
      id: crypto.randomUUID(), role: "human", text: draft,
      time: new Date().toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Bishkek" }),
    } }));
    setDrafts(values => ({ ...values, [id]: "" }));
  }

  function customerDetails() {
    return <>
      <div className="flex items-center justify-between"><h2 className="m-0 text-sm font-semibold">{c.customer}</h2><button type="button" aria-label={c.close} onClick={() => setDetailsOpen(false)} className={`${iconButton} xl:hidden`}><DashboardIcon name="close" size={18} /></button></div>
      <div className="mt-6 flex items-center gap-3"><span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-plumo-soft text-sm font-semibold text-plumo-blue">{selected.initials}</span><div><p className="m-0 text-sm font-semibold">{selected.name}</p><p className="mb-0 mt-1 text-xs text-plumo-muted">{selected.channel}</p></div></div>
      <dl className="mb-0 mt-6 space-y-5">
        {[[c.contact, selected.contact], [c.language, selected.language], [c.summary, selected.summary], [c.need, selected.need]].map(([label, value]) => <div key={label}><dt className="text-xs text-plumo-muted">{label}</dt><dd className="mb-0 ml-0 mt-1.5 break-words text-[13px] leading-6">{value}</dd></div>)}
      </dl>
      <div className="mt-6 rounded-xl bg-plumo-soft p-4"><h3 className="m-0 text-xs font-semibold text-plumo-blue">{c.next}</h3><p className="mb-0 mt-2 text-[13px] leading-6">{selected.next}</p></div>
    </>;
  }

  return <div className="flex h-full min-h-0 flex-col">
    <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 px-5 py-4 sm:px-6">
      <div className="flex items-center gap-3"><h1 className="m-0 text-xl font-semibold tracking-tight">{locale === "ru" ? "Диалоги" : "Conversations"}</h1><span className="rounded-md bg-plumo-line/60 px-2 py-1 text-xs text-plumo-muted">{conversations.length}</span></div>
      <span className="flex items-center gap-2 text-xs text-plumo-muted"><span className="size-1.5 rounded-full bg-amber-500" />{c.waiting}: {waitingCount}</span>
    </div>
    <div className="relative flex min-h-0 flex-1 overflow-hidden border-0 border-t border-solid border-plumo-line bg-white">
      <section aria-label={c.allModes} className={`${mobileChat ? "hidden" : "flex"} w-full shrink-0 flex-col border-0 border-r border-solid border-plumo-line md:flex md:w-[290px] 2xl:w-[330px]`}>
        <div className="space-y-3 p-4">
          <label className="relative block"><span className="pointer-events-none absolute left-3 top-3 text-plumo-muted"><DashboardIcon name="search" size={16} /></span><input type="search" aria-label={c.search} placeholder={locale === "ru" ? "Поиск диалогов" : "Search conversations"} value={search} onChange={event => setSearch(event.target.value)} className="h-10 w-full rounded-lg border border-solid border-plumo-line bg-plumo-line/20 pl-9 pr-3 font-[inherit] text-xs text-plumo-ink focus:outline-2 focus:outline-plumo-blue" /></label>
          <div className="flex gap-2">
            <select aria-label={c.all} value={channel} onChange={event => setChannel(event.target.value as Channel | "all")} className="min-w-0 flex-1 rounded-lg border border-solid border-plumo-line bg-white px-2 py-2 font-[inherit] text-xs text-plumo-ink focus:outline-plumo-blue"><option value="all">{c.all}</option>{(["WhatsApp", "Telegram", "Instagram"] as const).map(value => <option key={value}>{value}</option>)}</select>
            <select aria-label={c.allModes} value={mode} onChange={event => setMode(event.target.value as Mode | "all")} className="min-w-0 flex-1 rounded-lg border border-solid border-plumo-line bg-white px-2 py-2 font-[inherit] text-xs text-plumo-ink focus:outline-plumo-blue"><option value="all">{c.allModes}</option>{(["waiting", "ai", "human"] as const).map(value => <option key={value} value={value}>{c[value]}</option>)}</select>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {visible.map(item => <button key={item.id} type="button" aria-current={selectedId === item.id ? "true" : undefined} onClick={() => openConversation(item)} className={`mb-1 block w-full cursor-pointer rounded-xl border-0 p-3 text-left font-[inherit] transition-colors focus-visible:outline-2 focus-visible:outline-plumo-blue ${selectedId === item.id ? "bg-plumo-soft" : "bg-white hover:bg-plumo-line/30"}`}>
            <div className="flex items-center gap-2.5"><span className={`flex size-9 shrink-0 items-center justify-center rounded-xl text-xs font-medium ${selectedId === item.id ? "bg-white text-plumo-blue" : "bg-plumo-line/60 text-plumo-muted"}`}>{item.initials}</span><span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-plumo-ink">{item.name}</span><span className="text-[10px] text-plumo-muted">{item.messages.at(-1)?.time}</span></div>
            <p className="mb-2 mt-2 truncate text-xs leading-5 text-plumo-muted">{item.messages.filter(message => message.role !== "event").at(-1)?.text}</p>
            <div className="flex items-center justify-between gap-2"><ChannelBadge channel={item.channel} /><span className="flex items-center gap-1.5 text-[10px] text-plumo-muted">{c[item.mode]}{item.unread > 0 && <span aria-label={`${item.unread} ${c.unread}`} className="flex size-4 items-center justify-center rounded-full bg-plumo-blue text-[9px] text-white">{item.unread}</span>}</span></div>
          </button>)}
          {visible.length === 0 && <div className="px-4 py-12 text-center"><DashboardIcon name="search" /><h2 className="mb-0 mt-3 text-sm font-medium">{c.empty}</h2><p className="text-xs leading-5 text-plumo-muted">{c.emptyText}</p><button type="button" className={button} onClick={() => { setChannel("all"); setMode("all"); setSearch(""); }}>{c.clear}</button></div>}
        </div>
        <p className="m-0 border-0 border-t border-solid border-plumo-line px-4 py-3 text-[10px] leading-4 text-plumo-muted">{c.local}</p>
      </section>
      <section aria-label={c.messages} className={`${mobileChat ? "flex" : "hidden"} min-w-0 flex-1 flex-col md:flex`}>
        <div className="flex min-h-[78px] shrink-0 flex-wrap items-center justify-between gap-2 border-0 border-b border-solid border-plumo-line px-4 py-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-2"><button ref={backRef} type="button" aria-label={c.back} className={`${iconButton} md:hidden`} onClick={() => { setMobileChat(false); setDetailsOpen(false); }}><DashboardIcon name="back" size={18} /></button><div><h2 className="m-0 text-sm font-semibold">{selected.name}</h2><div className="mt-1 flex items-center gap-2 text-[10px] text-plumo-muted"><span>{selected.channel}</span><span>·</span><span role="status">{c[selected.mode]}</span></div></div></div>
          <div className="flex items-center gap-1.5"><button type="button" className={`cursor-pointer rounded-lg border border-solid px-3 py-2 font-[inherit] text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue ${selected.mode !== "human" ? "border-plumo-blue bg-plumo-blue text-white hover:bg-plumo-blue/90" : "border-plumo-line bg-white text-plumo-ink hover:bg-plumo-soft"}`} onClick={() => changeMode(selected.mode === "human" ? "ai" : "human")}>{selected.mode === "human" ? c.resume : c.take}</button><button type="button" aria-label={c.profile} aria-expanded={detailsOpen} aria-controls="customer-details" className={`${iconButton} xl:hidden`} onClick={() => setDetailsOpen(value => !value)}><DashboardIcon name="user" size={18} /></button></div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto bg-plumo-line/15 px-4 py-5 sm:px-6">
          <p className="mb-5 mt-0 text-center text-[10px] text-plumo-muted">{c.today}</p>
          <div className="flex flex-col gap-4">{selected.messages.map(message => message.role === "event" ? <p key={message.id} className="mx-auto my-1 max-w-[90%] rounded-lg bg-plumo-line/60 px-3 py-2 text-center text-[10px] leading-5 text-plumo-muted">{message.text}</p> : <div key={message.id} className={`flex max-w-[88%] flex-col sm:max-w-[80%] ${message.role === "customer" ? "self-start" : "self-end"}`}>
            <span className={`mb-1.5 text-[10px] text-plumo-muted ${message.role !== "customer" ? "text-right" : ""}`}>{message.role === "customer" ? selected.name : message.role === "ai" ? c.agent : c.manager}</span>
            <div className={`rounded-2xl px-4 py-3 ${message.role === "customer" ? "rounded-tl-sm border border-solid border-plumo-line bg-white" : "rounded-tr-sm bg-plumo-soft"}`}><p className="m-0 whitespace-pre-wrap break-words text-[13px] leading-[1.65] [overflow-wrap:anywhere]">{message.text}</p><p className="mb-0 mt-1.5 text-right text-[10px] text-plumo-muted">{message.time}</p></div>
          </div>)}</div><div ref={endRef} />
        </div>
        <form onSubmit={send} className="shrink-0 border-0 border-t border-solid border-plumo-line bg-white p-4">
          <p id="composer-hint" className="mb-2 mt-0 text-[11px] text-plumo-muted">{selected.mode === "human" ? `${c.sendingTo} ${selected.channel}` : c.locked}</p>
          <div className="flex items-end gap-2 rounded-xl border border-solid border-plumo-line p-2 focus-within:border-plumo-blue">
            <textarea aria-label={c.reply} aria-describedby="composer-hint" placeholder={c.reply} value={draft} maxLength={2000} rows={2} disabled={selected.mode !== "human"} onChange={event => setDrafts(values => ({ ...values, [selected.id]: event.target.value }))} className="min-w-0 flex-1 resize-none border-0 bg-transparent p-1.5 font-[inherit] text-[13px] leading-5 text-plumo-ink outline-none disabled:cursor-not-allowed disabled:opacity-50" />
            <button type="submit" aria-label={c.send} title={c.send} disabled={selected.mode !== "human" || !draft.trim()} className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg border-0 bg-plumo-blue text-white hover:bg-plumo-blue/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-not-allowed disabled:bg-plumo-line disabled:text-plumo-muted"><DashboardIcon name="send" size={17} /></button>
          </div>
        </form>
      </section>
      <aside id="customer-details" aria-label={c.details} className={`${detailsOpen ? "absolute inset-y-0 right-0 z-10 block w-full max-w-[300px] shadow-xl" : "hidden"} overflow-y-auto border-0 border-l border-solid border-plumo-line bg-white p-5 xl:static xl:block xl:w-[264px] xl:shrink-0 xl:shadow-none`} onKeyDown={event => { if (event.key === "Escape") setDetailsOpen(false); }}>{customerDetails()}</aside>
    </div>
  </div>;
}
