"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api/client";
import { useLanguage } from "@/lib/i18n";

type Result = { text: string; handoff: boolean; model: string; mock: boolean; sources: { id: string; title: string }[] };
type Turn = { id: string; text: string; status: "pending" | "succeeded" | "failed"; error: string | null; result: Result | null };
type Summary = { id: string; created_at: string; paused: boolean; messages: number };
type Detail = Summary & { turns: Turn[] };
type Listing = { sessions: Summary[]; mock: boolean; published: boolean; limits: { used_messages: number; daily_messages: number; session_messages: number; charged_usd: number; daily_budget_usd: number } };
type Pending = { request_id: string; text: string };

const button = "inline-flex min-h-10 cursor-pointer items-center justify-center rounded-xl border border-solid border-plumo-line bg-white px-4 py-2 font-[inherit] text-[13px] text-plumo-ink disabled:cursor-default disabled:opacity-50";

export function AgentTestChat({ prepare }: { prepare?: () => Promise<boolean> }) {
  const { locale } = useLanguage();
  const ru = locale === "ru";
  const [listing, setListing] = useState<Listing | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [text, setText] = useState("");
  const [uncertain, setUncertain] = useState<Pending | null>(null);
  const [sending, setSending] = useState<Pending | null>(null);
  const selected = useRef<string | null>(null);
  const locked = useRef(false);
  const mounted = useRef(true);
  const newId = useRef<string | null>(null);
  const transcript = useRef<HTMLDivElement>(null);

  function message(error: unknown) {
    const code = error instanceof ApiError ? error.code : "network_error";
    const labels: Record<string, [string, string]> = {
      test_limit: ["Лимит тестов достигнут. Можно продолжить завтра или начать новый тест, если исчерпан только текущий диалог.", "Test allowance reached. Try tomorrow, or start a new test if only this conversation is full."],
      test_session_limit: ["Дневной лимит новых тестов достигнут. Продолжите завтра.", "Daily limit for new tests reached. Continue tomorrow."],
      test_setup_required: ["Сначала завершите настройку бизнеса и опубликуйте материалы.", "Complete the business setup and publish your materials first."],
      test_settings_changed: ["Настройки обновились. Начните новый тест, чтобы проверить новую версию.", "Settings changed. Start a new test to use the new version."],
      test_paused: ["Сценарий передан человеку. Начните новый тест.", "The scenario was handed off. Start a new test."],
      test_busy: ["Предыдущий запрос ещё обрабатывается. Обновите историю.", "The previous request is still processing. Refresh the history."],
      not_authenticated: ["Сессия завершена. Войдите снова.", "Your session ended. Sign in again."],
      network_error: ["Связь прервалась. Проверьте отправку — повторного списания за тот же запрос не будет.", "Connection lost. Check the send status; the same request will not be charged twice."],
    };
    return (labels[code] ?? ["Не удалось выполнить запрос. Обновите историю и повторите попытку.", "Request failed. Refresh the history and try again."])[ru ? 0 : 1];
  }

  async function refresh(id = selected.current) {
    const next = await api<Listing>("testing/sessions");
    if (!mounted.current) return;
    setListing(next);
    const pick = id ?? next.sessions[0]?.id;
    if (pick) {
      selected.current = pick;
      const value = await api<Detail>(`testing/sessions/${pick}`);
      if (mounted.current && selected.current === pick) {
        setDetail(value);
        setUncertain(current => current && !value.turns.some(turn => turn.id === current.request_id && turn.status !== "pending") ? current : null);
      }
    }
  }

  useEffect(() => {
    mounted.current = true;
    void refresh().catch(e => { if (mounted.current) setError(message(e)); }).finally(() => { if (mounted.current) setLoading(false); });
    return () => { mounted.current = false; };
  }, []);

  const pending = detail?.turns.some(turn => turn.status === "pending") ?? false;
  useEffect(() => {
    if (!pending || !detail) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let delay = 2000;
    const poll = async () => {
      try {
        const next = await api<Detail>(`testing/sessions/${detail.id}`, { signal: controller.signal });
        if (controller.signal.aborted || selected.current !== next.id) return;
        setDetail(next);
        if (!next.turns.some(turn => turn.status === "pending")) { void refresh(next.id).catch(() => {}); return; }
        delay = 2000;
      } catch {
        if (controller.signal.aborted) return;
        delay = Math.min(10000, delay * 2);
      }
      timer = setTimeout(poll, delay);
    };
    timer = setTimeout(poll, delay);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [pending, detail?.id]);

  useEffect(() => { if (transcript.current) transcript.current.scrollTop = transcript.current.scrollHeight; }, [detail?.turns.length, sending, pending]);

  async function start() {
    if (locked.current || pending || uncertain) return;
    locked.current = true; setBusy(true); setError("");
    try {
      if (prepare && !(await prepare())) { setError(ru ? "Не удалось применить настройки. Проверьте поля и сохранение мастера." : "Could not apply settings. Check the wizard fields and save status."); return; }
      newId.current ??= crypto.randomUUID();
      const next = await api<Detail>("testing/sessions", { method: "POST", body: { id: newId.current } });
      if (!mounted.current) return;
      selected.current = next.id; setDetail(next); setText(""); setUncertain(null); newId.current = null;
      await refresh(next.id);
    } catch (e) { if (mounted.current) setError(message(e)); }
    finally { locked.current = false; if (mounted.current) setBusy(false); }
  }

  async function send(replay?: Pending) {
    if (locked.current || !detail || pending || (detail.paused && !replay)) return;
    const request = replay ?? { request_id: crypto.randomUUID(), text: text.trim() };
    if (!request.text) return;
    locked.current = true; setBusy(true); setError(""); setSending(request); setText("");
    try {
      await api<Turn>(`testing/sessions/${detail.id}/messages`, { method: "POST", body: request });
      await refresh(detail.id);
      if (mounted.current) setUncertain(null);
    } catch (e) {
      if (!mounted.current) return;
      setError(message(e));
      if (!(e instanceof ApiError) || e.unavailable || e.status >= 500) setUncertain(request);
      else { setUncertain(null); setText(request.text); }
    } finally { locked.current = false; if (mounted.current) { setBusy(false); setSending(null); } }
  }

  const last = detail?.turns.at(-1);
  const disabled = busy || pending || !!uncertain;
  const optimistic = sending && !detail?.turns.some(turn => turn.id === sending.request_id);
  return <section aria-label={ru ? "Тест агента" : "Agent test"} className="min-w-0 overflow-hidden rounded-[20px] border border-solid border-plumo-line bg-white text-plumo-ink">
    <div className="flex flex-wrap items-center gap-3 border-0 border-b border-solid border-plumo-line p-4">
      <div className="mr-auto"><h2 className="m-0 text-[17px] font-medium">{ru ? "Тест агента" : "Agent test"}</h2><p className="mb-0 mt-1 text-[12px] text-plumo-muted">{ru ? "История тестов отдельно от клиентов. Заявки и уведомления не отправляются." : "Test history is separate from customers. No bookings or notifications are sent."}</p></div>
      <button type="button" disabled={disabled || loading} className={button} onClick={() => void start()}>{busy ? (ru ? "Подождите…" : "Please wait…") : prepare ? (ru ? "Применить настройки и начать тест" : "Apply settings and start a test") : (ru ? "Новый тест" : "New test")}</button>
    </div>
    <div className="space-y-3 p-4">
      {listing && <><p className="m-0 text-[12px] text-plumo-muted">{ru ? "Сегодня использовано" : "Used today"}: {listing.limits.used_messages}/{listing.limits.daily_messages} · {ru ? "бюджет тестов" : "test allowance"}: ${listing.limits.charged_usd.toFixed(2)}/${listing.limits.daily_budget_usd.toFixed(2)} · {ru ? "до" : "up to"} {listing.limits.session_messages} {ru ? "сообщений в диалоге" : "messages per conversation"}</p>
      {listing.mock && <p role="status" className="m-0 rounded-xl bg-plumo-soft p-3 text-[13px]">{ru ? "Сейчас используется демонстрационная модель. Для проверки ответов ИИ подключите рабочую модель." : "A demo model is currently active. Connect a live model to test AI replies."}</p>}
      {!listing.published && !prepare && <p className="m-0 text-[14px]"><Link href="/create/wizard" className="text-plumo-blue underline">{ru ? "Завершить настройку бизнеса" : "Complete business setup"}</Link></p>}
      {listing.sessions.length > 0 && <label className="flex flex-wrap items-center gap-2 text-[12px] text-plumo-muted">{ru ? "История тестов" : "Test history"}<select aria-label={ru ? "Выбрать тест" : "Select test"} value={detail?.id ?? ""} disabled={disabled} onChange={e => { selected.current = e.target.value; setError(""); void refresh(e.target.value).catch(err => setError(message(err))); }} className="max-w-full rounded-lg border border-solid border-plumo-line bg-white p-2 font-[inherit] text-plumo-ink"><option value="" disabled>{ru ? "Выберите тест" : "Select a test"}</option>{listing.sessions.map((item, index) => <option key={item.id} value={item.id}>{ru ? "Тест" : "Test"} {listing.sessions.length - index} · {item.created_at.slice(0, 16).replace("T", " ")} UTC</option>)}</select></label>}</>}
    </div>
    <div ref={transcript} role="log" aria-live="polite" aria-label={ru ? "Переписка теста" : "Test conversation"} aria-busy={busy || pending} className="flex h-[340px] flex-col gap-4 overflow-y-auto bg-plumo-line/10 p-4">
      {loading && <p role="status" className="m-0 text-[14px] text-plumo-muted">{ru ? "Загружаем тесты…" : "Loading tests…"}</p>}
      {!loading && !detail && <p className="m-0 text-[14px] leading-relaxed text-plumo-muted">{ru ? "Начните тест, затем задайте агенту вопрос о своём бизнесе." : "Start a test, then ask the agent about your business."}</p>}
      {detail && detail.turns.length === 0 && <p className="m-0 text-[14px] text-plumo-muted">{ru ? "Напишите первое сообщение, например «Здравствуйте»." : "Send the first message, for example “Hello”."}</p>}
      {detail?.turns.map(turn => <div key={turn.id} className="flex flex-col gap-3">
        <p className="m-0 max-w-[90%] self-end whitespace-pre-wrap break-words rounded-2xl rounded-tr-sm bg-plumo-ink px-4 py-3 text-[14px] text-white">{turn.text}</p>
        {turn.result && <div className="max-w-[90%] self-start rounded-2xl rounded-tl-sm border border-solid border-plumo-line bg-white px-4 py-3"><p className="m-0 whitespace-pre-wrap break-words text-[14px] leading-relaxed">{turn.result.text}</p>{turn.result.sources.length > 0 && <p className="mb-0 mt-2 text-[11px] text-plumo-muted">{ru ? "Материалы" : "Sources"}: {turn.result.sources.map(source => source.title).join(", ")}</p>}{turn.result.handoff && <p className="mb-0 mt-2 text-[12px] text-plumo-muted">{ru ? "Проверка передачи человеку: реальный менеджер не уведомлён." : "Simulated handoff: no real manager was notified."}</p>}</div>}
        {turn.status === "pending" && <p role="status" className="m-0 text-[13px] text-plumo-muted">{ru ? "Агент готовит ответ…" : "The agent is preparing a reply…"}</p>}
        {turn.status === "failed" && <p className="m-0 rounded-xl bg-plumo-soft p-3 text-[13px]">{ru ? "Ответ не получен. Можно повторить сообщение; это будет новая попытка в пределах лимита." : "No reply received. You can retry as a new attempt within the allowance."}</p>}
      </div>)}
      {optimistic && <p className="m-0 max-w-[90%] self-end whitespace-pre-wrap break-words rounded-2xl bg-plumo-ink px-4 py-3 text-[14px] text-white">{sending.text}</p>}
      {busy && !pending && <p role="status" className="m-0 text-[13px] text-plumo-muted">{ru ? "Выполняем запрос…" : "Processing…"}</p>}
    </div>
    <div className="space-y-3 border-0 border-t border-solid border-plumo-line p-4">
      {error && <p role="alert" className="m-0 text-[13px] text-red-700">{error}</p>}
      {uncertain && <button type="button" className={button} disabled={busy || pending} onClick={() => void send(uncertain)}>{ru ? "Проверить отправку" : "Check send status"}</button>}
      {last?.status === "failed" && !uncertain && <button type="button" className={button} disabled={disabled} onClick={() => void send({ request_id: crypto.randomUUID(), text: last.text })}>{ru ? "Повторить последнее сообщение" : "Retry last message"}</button>}
      {detail?.paused ? <p role="status" className="m-0 text-[14px]">{ru ? "Агент остановлен после передачи человеку. Для продолжения начните новый тест." : "Agent paused after handoff. Start a new test to continue."}</p> : <form onSubmit={event => { event.preventDefault(); void send(); }} className="flex gap-2"><input aria-label={ru ? "Сообщение агенту" : "Message to agent"} value={text} onChange={event => setText(event.target.value)} disabled={!detail || disabled} maxLength={1000} placeholder={ru ? "Задайте вопрос о бизнесе" : "Ask about your business"} className="min-w-0 flex-1 rounded-xl border border-solid border-plumo-line bg-white px-3 py-3 font-[inherit] text-[16px] text-plumo-ink disabled:opacity-50" /><button type="submit" disabled={!detail || disabled || !text.trim()} className={`${button} !border-plumo-ink !bg-plumo-ink !text-white`}>{ru ? "Отправить" : "Send"}</button></form>}
      {error && !busy && <button type="button" className={button} onClick={() => { setError(""); void refresh().catch(e => setError(message(e))); }}>{ru ? "Обновить историю" : "Refresh history"}</button>}
    </div>
  </section>;
}
