"use client";
import { useCallback, useState } from "react";
import { ApiError, api, goToLogin } from "@/lib/api/client";
import { usePolling } from "@/lib/api/use-polling";
import { useLanguage } from "@/lib/i18n";
import { apiErrorText } from "./api-messages";
import { formatTime } from "./dialogue-model";
import { statisticsPeriod, validStatisticsPeriod } from "./statistics-model";

const keys = ["conversations", "agent_replies", "handoffs", "manager_replies", "failed", "unknown"] as const;
type Counts = Record<typeof keys[number], number>;
type StatisticsData = { date_from: string; date_to: string; timezone: string; generated_at: string; totals: Counts; days: (Counts & { day: string })[]; logged_ai_estimate_usd: number | null; logged_interactions: number; mock_interactions: number; cost_coverage: string };
const control = "rounded-lg border border-solid border-plumo-line bg-white px-3 py-2 font-[inherit] text-sm text-plumo-ink focus-visible:outline-2 focus-visible:outline-plumo-blue";

export function Statistics({ active }: { active: boolean }) {
  const { locale } = useLanguage();
  const ru = locale === "ru";
  const [draft, setDraft] = useState(() => statisticsPeriod());
  const [period, setPeriod] = useState(draft);
  const [data, setData] = useState<StatisticsData | null>(null);
  const [error, setError] = useState("");
  const [formError, setFormError] = useState(false);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async (signal: AbortSignal) => {
    setLoading(true);
    try {
      const value = await api<StatisticsData>("dashboard/statistics", { query: { date_from: period.from, date_to: period.to }, signal });
      if (!signal.aborted) { setData(value); setError(""); }
    } catch (reason) {
      if (signal.aborted) return;
      if (reason instanceof ApiError && reason.unauthenticated) goToLogin();
      setError(reason instanceof ApiError ? apiErrorText(reason.code, locale) : ru ? "Не удалось загрузить статистику." : "Could not load statistics.");
      throw reason;
    } finally { if (!signal.aborted) setLoading(false); }
  }, [period.from, period.to, locale, ru]);
  const refresh = usePolling(load, 30000, `${period.from}|${period.to}`, active);
  const current = data?.date_from === period.from && data.date_to === period.to ? data : null;
  const labels: Record<typeof keys[number], string> = ru
    ? { conversations: "Новые диалоги", agent_replies: "Создано ответов агента", handoffs: "Запросы передачи", manager_replies: "Ответы менеджера", failed: "Неуспешные отправки", unknown: "Неизвестная доставка" }
    : { conversations: "New conversations", agent_replies: "Agent replies created", handoffs: "Handoff requests", manager_replies: "Manager replies", failed: "Failed deliveries", unknown: "Unknown delivery" };
  const empty = current && keys.every(key => current.totals[key] === 0) && current.logged_interactions === 0;
  return <section aria-label={ru ? "Статистика" : "Statistics"} className="h-full overflow-y-auto p-4 text-plumo-ink md:p-6"><div className="mx-auto max-w-6xl">
    <h1 className="m-0 text-xl font-semibold">{ru ? "Статистика пилота" : "Pilot statistics"}</h1>
    <p className="mb-4 mt-2 text-sm leading-6 text-plumo-muted">{ru ? "Telegram, Instagram и WhatsApp · время Бишкека (UTC+6). Обе даты включены в период. Тестовые чаты и голос исключены." : "Telegram, Instagram and WhatsApp · Bishkek time (UTC+6). Both dates are included. Sandbox chats and voice are excluded."}</p>
    <form className="mb-4 flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); if (!validStatisticsPeriod(draft.from, draft.to)) { setFormError(true); return; } setFormError(false); if (period.from === draft.from && period.to === draft.to) refresh(); else setPeriod({ ...draft }); }}>
      <label className="flex flex-col gap-1 text-xs text-plumo-muted">{ru ? "С даты" : "From"}<input type="date" required min="2000-01-01" max="2100-12-31" value={draft.from} onChange={event => setDraft(value => ({ ...value, from: event.target.value }))} className={control} /></label>
      <label className="flex flex-col gap-1 text-xs text-plumo-muted">{ru ? "По дату" : "To"}<input type="date" required min="2000-01-01" max="2100-12-31" value={draft.to} onChange={event => setDraft(value => ({ ...value, to: event.target.value }))} className={control} /></label>
      <button type="submit" className={`${control} cursor-pointer hover:bg-plumo-soft`}>{ru ? "Показать" : "Apply"}</button>
      <button type="button" className={`${control} cursor-pointer hover:bg-plumo-soft`} onClick={refresh}>{ru ? "Обновить" : "Refresh"}</button>
    </form>
    {formError && <p role="alert" className="text-sm text-red-700">{ru ? "Выберите период от 1 до 92 дней; начальная дата не должна быть позже конечной." : "Choose 1–92 days; the start date must not follow the end date."}</p>}
    {error && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">{error} {current ? (ru ? "Показан последний загруженный снимок." : "Showing the last loaded snapshot.") : ""}</p>}
    {loading && <p role="status" className="text-sm text-plumo-muted">{ru ? "Обновляем показатели…" : "Updating statistics…"}</p>}
    {current && <>
      <p className="text-xs text-plumo-muted">{period.from} — {period.to} · {ru ? "Снимок" : "Snapshot"}: {formatTime(current.generated_at, locale)}</p>
      {empty && <p role="status" className="rounded-xl bg-plumo-soft p-4 text-sm">{ru ? "За этот период событий нет." : "No events in this period."}</p>}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">{keys.map(key => <div key={key} className="rounded-xl border border-solid border-plumo-line bg-white p-4"><p className="m-0 text-xs leading-5 text-plumo-muted">{labels[key]}</p><p className="mb-0 mt-2 text-2xl font-semibold tabular-nums">{current.totals[key]}</p></div>)}</div>
      <div className="mt-4 rounded-xl border border-solid border-plumo-line bg-white p-4 text-sm leading-6"><p className="m-0 font-medium">{ru ? "Оценка из журнала ИИ" : "AI journal estimate"}: {current.logged_ai_estimate_usd === null ? (ru ? "нет данных" : "no data") : `$${current.logged_ai_estimate_usd.toFixed(6)}`}</p><p className="mb-0 mt-2 text-plumo-muted">{ru ? "Записей обработки" : "Logged interactions"}: {current.logged_interactions} · {ru ? "из них демонстрационные" : "demo entries"}: {current.mock_interactions}. {ru ? "Это частичная оценка, не счёт провайдера и не общий бюджет. Полный учёт расходов и бюджета пока недоступен." : "This is a partial estimate, not a provider invoice or total budget. Full expense and budget accounting is not available yet."}</p></div>
      <details className="mt-4 rounded-xl border border-solid border-plumo-line bg-white p-4 text-sm leading-6"><summary className="cursor-pointer font-medium">{ru ? "Как считаются показатели" : "Metric definitions"}</summary><p>{ru ? "Диалоги — по началу. Ответы агента и менеджера — по сохранённым сообщениям; это не подтверждение доставки или прочтения. Передачи — число созданных запросов, не число уникальных клиентов." : "Conversations use their start date. Agent and manager replies count stored messages, not delivery or read receipts. Handoffs count created requests, not unique customers."}</p><p className="mb-0">{ru ? "Неуспешные отправки и неизвестная доставка — текущий статус отправок, созданных в периоде. Повторная попытка одной отправки не считается новой записью. Эти значения могут измениться после повтора или ручного решения. События деморежима в каналах учитываются; изолированные тестовые сессии исключены. Время первого ответа пока не рассчитывается." : "Failed and unknown are current statuses of deliveries created in the period. Retrying one delivery does not add a record. Counts may change after retry or manual resolution. Demo-mode channel events are included; isolated test sessions are excluded. First-response time is not calculated yet."}</p></details>
      <div className="mt-5 overflow-x-auto rounded-xl border border-solid border-plumo-line bg-white"><table className="w-full border-collapse text-left text-xs"><caption className="p-3 text-left text-sm font-medium">{ru ? "По дням Бишкека" : "By Bishkek day"}</caption><thead><tr><th scope="col" className="p-3">{ru ? "Дата" : "Date"}</th>{keys.map(key => <th key={key} scope="col" className="p-3">{labels[key]}</th>)}</tr></thead><tbody>{current.days.map(day => <tr key={day.day} className="border-0 border-t border-solid border-plumo-line"><th scope="row" className="whitespace-nowrap p-3 font-normal">{day.day}</th>{keys.map(key => <td key={key} className="p-3 tabular-nums">{day[key]}</td>)}</tr>)}</tbody></table></div>
    </>}
  </div></section>;
}
