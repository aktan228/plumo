"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, goToLogin } from "@/lib/api/client";
import { usePolling } from "@/lib/api/use-polling";
import { useLanguage } from "@/lib/i18n";
import { channelName, formatTime } from "./dialogue-model";
import { loadColumn, moveCard, stages, type Board, type BoardCard, type Column, type Stage } from "./kanban-model";

const control = "rounded-lg border border-solid border-plumo-line bg-white px-3 py-2 font-[inherit] text-xs text-plumo-ink focus-visible:outline-2 focus-visible:outline-plumo-blue disabled:opacity-50";
export function Kanban({ onOpen }: { onOpen: (id: string) => void }) {
  const { locale } = useLanguage();
  const ru = locale === "ru";
  const names: Record<Stage, string> = ru ? { unassigned: "Без стадии", new: "Новый", discovery: "Выяснение потребности", qualified: "Квалифицирован", meeting_requested: "Запрошена встреча", meeting_confirmed: "Встреча подтверждена" } : { unassigned: "No stage", new: "New", discovery: "Discovery", qualified: "Qualified", meeting_requested: "Meeting requested", meeting_confirmed: "Meeting confirmed" };
  const modeNames: Record<BoardCard["mode"], string> = ru ? { ai: "Режим агента", human: "Режим менеджера", waiting: "Нужен менеджер" } : { ai: "Agent mode", human: "Manager mode", waiting: "Needs a manager" };
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [channel, setChannel] = useState("");
  const [mode, setMode] = useState("");
  const filterKey = `${query}|${channel}|${mode}`;
  const [windowSize, setWindowSize] = useState<{ key: string; counts: Partial<Record<Stage, number>> }>({ key: "", counts: {} });
  const counts = windowSize.key === filterKey ? windowSize.counts : {};
  const loadKey = `${filterKey}|${stages.map(stage => counts[stage] ?? 30).join(",")}`;
  const [snapshot, setSnapshot] = useState<{ key: string; board: Board } | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const moving = useRef(false);
  const generation = useRef(0);
  const dragged = useRef<{ card: BoardCard; key: string } | null>(null);
  const board = snapshot?.key === loadKey ? snapshot.board : null;
  useEffect(() => { const timer = setTimeout(() => setQuery(search.trim()), 300); return () => clearTimeout(timer); }, [search]);
  const load = useCallback(async (signal: AbortSignal) => {
    if (moving.current) return;
    const started = generation.current;
    setLoading(true);
    try {
      const columns = await Promise.all(stages.map(stage => loadColumn(counts[stage] ?? 30,
        (limit, cursor) => api<Column>("dashboard/kanban", { signal, query: { stage, q: query, channel, mode, limit, cursor } }))));
      if (!signal.aborted && !moving.current && started === generation.current) {
        setSnapshot({ key: loadKey, board: Object.fromEntries(columns.map(column => [column.stage, column])) as Board });
        setLoadError(false);
      }
    } catch (reason) {
      if (signal.aborted) return;
      if (reason instanceof ApiError && reason.unauthenticated) goToLogin();
      setLoadError(true);
      throw reason;
    } finally { if (!signal.aborted) setLoading(false); }
  }, [loadKey]);
  const refresh = usePolling(load, 10000, loadKey);

  async function move(card: BoardCard, target: Stage) {
    if (!board || moving.current || card.pipeline_stage === target) return;
    let confirmed = false;
    if (target === "meeting_confirmed") {
      confirmed = window.confirm(ru ? "Менеджер подтвердил дату и время встречи с клиентом? Эта стадия не бронирует календарь." : "Has a manager confirmed the meeting date and time with the customer? This stage does not book a calendar.");
      if (!confirmed) return;
    }
    const previous = board;
    moving.current = true; generation.current += 1; setBusy(true); setNotice("");
    setSnapshot({ key: loadKey, board: moveCard(previous, card, target) });
    try {
      await api(`conversations/${card.id}/stage`, { method: "PATCH", body: { stage: target, version: card.stage_version, confirm_meeting: confirmed } });
      setNotice(ru ? "Стадия сохранена." : "Stage saved.");
    } catch (reason) {
      setSnapshot({ key: loadKey, board: previous });
      if (reason instanceof ApiError && reason.unauthenticated) goToLogin();
      setNotice(reason instanceof ApiError && reason.code === "version_conflict"
        ? (ru ? "Стадия уже изменена другим оператором. Загружаем актуальную доску." : "Another operator changed the stage. Reloading the board.")
        : (ru ? "Результат изменения не подтверждён. Отменили предварительное перемещение и перепроверяем сервер." : "The result is unconfirmed. Reverted the preview and rechecking the server."));
    } finally { moving.current = false; setBusy(false); refresh(); }
  }
  return <section aria-label={ru ? "Канбан диалогов" : "Conversation Kanban"} className="flex h-full min-h-0 flex-col p-4 text-plumo-ink">
    <p className="mb-3 mt-0 text-xs leading-5 text-plumo-muted">{ru ? "Стадия не меняет режим ответов. Перетащите карточку или выберите стадию в её списке. Встреча подтверждается менеджером отдельно." : "Stage does not change who replies. Drag a card or choose its stage from the selector. A manager must confirm meetings separately."}</p>
    <div className="mb-3 flex flex-wrap gap-2"><input type="search" maxLength={100} disabled={busy} aria-label={ru ? "Поиск карточек" : "Search cards"} placeholder={ru ? "Поиск по имени, контакту или сообщению" : "Search name, contact or message"} value={search} onChange={event => setSearch(event.target.value)} className={`${control} min-w-0 flex-1 text-base`} />
      <select disabled={busy} aria-label={ru ? "Канал" : "Channel"} value={channel} onChange={event => setChannel(event.target.value)} className={control}><option value="">{ru ? "Все каналы" : "All channels"}</option>{["telegram", "instagram", "whatsapp"].map(value => <option key={value} value={value}>{channelName(value)}</option>)}</select>
      <select disabled={busy} aria-label={ru ? "Режим диалога" : "Conversation mode"} value={mode} onChange={event => setMode(event.target.value)} className={control}><option value="">{ru ? "Все режимы" : "All modes"}</option>{(["ai", "human", "waiting"] as const).map(value => <option key={value} value={value}>{modeNames[value]}</option>)}</select>
      <button type="button" disabled={busy} className={`${control} cursor-pointer`} onClick={refresh}>{ru ? "Обновить" : "Refresh"}</button>
    </div>
    {loadError && <p role="alert" className="mb-3 mt-0 text-xs text-amber-800">{ru ? "Не удалось обновить доску. Последние данные могут быть устаревшими." : "Could not refresh the board. Displayed data may be out of date."}</p>}
    <p role="status" className="mb-2 mt-0 text-xs text-plumo-muted">{busy ? (ru ? "Сохраняем…" : "Saving…") : notice || (loading ? (ru ? "Обновляем…" : "Refreshing…") : "")}</p>
    <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto pb-2">{stages.map(stage => <section key={stage} aria-label={names[stage]} onDragOver={event => { if (dragged.current && !busy) event.preventDefault(); }} onDrop={event => { event.preventDefault(); const source = dragged.current; dragged.current = null; if (source?.key === filterKey) void move(source.card, stage); }} className="flex w-[270px] shrink-0 flex-col rounded-xl border border-solid border-plumo-line bg-plumo-line/20">
      <h2 className="m-0 flex items-center justify-between gap-2 p-3 text-xs font-semibold">{names[stage]} <span className="font-normal text-plumo-muted">{board ? board[stage].total : "…"}</span></h2>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
        {board?.[stage].items.map(card => <article key={card.id} draggable={!busy} onDragStart={event => { if (moving.current) { event.preventDefault(); return; } dragged.current = { card, key: filterKey }; event.dataTransfer.setData("text/plain", card.id); event.dataTransfer.effectAllowed = "move"; }} onDragEnd={() => { dragged.current = null; }} className="rounded-lg border border-solid border-plumo-line bg-white p-3 shadow-sm">
          <button type="button" disabled={busy} className="w-full cursor-pointer border-0 bg-transparent p-0 text-left font-[inherit] text-xs text-plumo-ink focus-visible:outline-2 focus-visible:outline-plumo-blue disabled:opacity-50" onClick={() => onOpen(card.id)}><strong className="block break-words">{card.name || card.handle || card.phone || (ru ? "Клиент без имени" : "Unnamed customer")}</strong><span className="mt-1 block text-[10px] text-plumo-muted">{channelName(card.channel)} · {modeNames[card.mode]} · {formatTime(card.activity_at, locale)}</span><span className="mt-2 block break-words text-xs leading-5 text-plumo-muted">{card.preview || (ru ? "Сообщений пока нет" : "No messages yet")}</span></button>
          <label className="mt-3 block text-[10px] text-plumo-muted">{ru ? "Стадия" : "Stage"}<select disabled={busy} value={card.pipeline_stage} onChange={event => void move(card, event.target.value as Stage)} className={`${control} mt-1 w-full px-2`}>{stages.map(value => <option key={value} value={value}>{names[value]}</option>)}</select></label>
        </article>)}
        {board && board[stage].total === 0 && <p className="p-3 text-center text-xs text-plumo-muted">{ru ? "Нет подходящих диалогов" : "No matching conversations"}</p>}
        {board?.[stage].next_cursor && <button type="button" disabled={busy || loading} className={`${control} w-full cursor-pointer`} onClick={() => setWindowSize({ key: filterKey, counts: { ...counts, [stage]: (counts[stage] ?? 30) + 30 } })}>{ru ? "Показать ещё" : "Load more"}</button>}
      </div>
    </section>)}</div>
  </section>;
}
