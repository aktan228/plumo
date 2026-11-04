"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api/client";
import { usePolling } from "@/lib/api/use-polling";
import { useLanguage } from "@/lib/i18n";
import { formatTime } from "./dialogue-model";
import { dashboardIssue, improvementHref, conversationHref, testingHref, knowledgeHref } from "./navigation";
import { categoryNames, statusNames, eligibleVerification, improvementError, newerIssue, type Category, type IssueStatus } from "./improvement-model";

type Evidence = { id: string; title: string; updated_at: string | null; content_sha256: string | null };
type Verification = { test_session_id: string; test_request_id: string; question: string; answer: string; scope: string; note: string; publication_version: number };
type Issue = { id: string; category: Category; note: string; status: IssueStatus; version: number; created_at: string; fixed_at: string | null; fixed_publication_version: number | null; correction_note: string | null; current_publication_version: number | null; verification_current: boolean; verification: Verification | null;
  snapshot: { kind: "message" | "test"; conversation_id?: string; test_session_id?: string; answer: string; question: string | null; publication_version: number | null; model: string; source_versions: Evidence[] };
  history: { status: IssueStatus; at: string; note?: string; verification?: Verification | null }[] };
type Page = { items: Issue[]; next_cursor: string | null };
type Session = { id: string; publication_version: number; created_at: string };
type Turn = { id: string; text: string; status: string; result: { text: string; mock: boolean; model: string } | null };
const control = "rounded-lg border border-solid border-plumo-line bg-white px-3 py-2 font-[inherit] text-sm text-plumo-ink focus-visible:outline-2 focus-visible:outline-plumo-blue disabled:opacity-50";

export function Improvements({ active }: { active: boolean }) {
  const { locale } = useLanguage();
  const ru = locale === "ru";
  const [status, setStatus] = useState("");
  const [pages, setPages] = useState<{ status: string; cursors: string[] }>({ status: "", cursors: [] });
  const cursors = pages.status === status ? pages.cursors : [];
  const cursor = cursors.at(-1);
  const listKey = `${status}|${cursor ?? ""}`;
  const [list, setList] = useState<{ key: string; data: Page } | null>(null);
  const [listError, setListError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Issue | null>(null);
  const [error, setError] = useState("");
  type Draft = { id: string; version: number; text: string };
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const draft = selected ? drafts[selected] ?? null : null;
  function setDraft(next: Draft | null | ((previous: Draft | null) => Draft)) {
    setDrafts(values => {
      const value = typeof next === "function" ? next(selected ? values[selected] ?? null : null) : next;
      if (value) return { ...values, [value.id]: value };
      const remaining = { ...values };
      if (selected) delete remaining[selected];
      return remaining;
    });
  }
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const selectedRef = useRef<string | null>(null);
  useEffect(() => { selectedRef.current = selected; }, [selected]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [turnId, setTurnId] = useState("");
  const [testRevision, setTestRevision] = useState(0);
  useEffect(() => {
    if (!active) return;
    const read = () => setSelected(dashboardIssue(window.location.search));
    read(); window.addEventListener("popstate", read);
    return () => window.removeEventListener("popstate", read);
  }, [active]);
  useEffect(() => {
    if (!Object.values(drafts).some(value => value.text.trim())) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [drafts]);
  const loadList = useCallback(async (signal: AbortSignal) => {
    try {
      const data = await api<Page>("improvements", { signal, query: { status, cursor, limit: 20 } });
      if (!signal.aborted) { setList({ key: listKey, data }); setListError(""); }
    } catch (reason) { if (!signal.aborted) setListError(improvementError(reason instanceof ApiError ? reason.code : "network_error", ru)); throw reason; }
  }, [listKey, ru]);
  const refreshList = usePolling(loadList, 15000, listKey, active);
  const loadDetail = useCallback(async (signal: AbortSignal) => {
    if (!selected) return;
    try {
      const value = await api<Issue>(`improvements/${selected}`, { signal });
      if (!signal.aborted && selectedRef.current === value.id) setDetail(previous => newerIssue(previous, value));
    } catch (reason) {
      if (!signal.aborted) {
        if (reason instanceof ApiError && reason.status === 404) setDetail(null);
        setError(improvementError(reason instanceof ApiError ? reason.code : "network_error", ru));
      }
      throw reason;
    }
  }, [selected, ru]);
  const refreshDetail = usePolling(loadDetail, 10000, selected ?? "none", active && !!selected);
  const current = detail?.id === selected ? detail : null;
  useEffect(() => { setSessionId(""); setTurnId(""); setTurns([]); setSessions([]); setError(""); }, [selected]);
  useEffect(() => {
    if (!active || current?.status !== "fixed") return;
    const controller = new AbortController();
    api<{ sessions: Session[] }>("testing/sessions", { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setSessions(data.sessions.filter(session => eligibleVerification(session, current.fixed_publication_version, current.fixed_at)));
    }).catch(reason => { if (!controller.signal.aborted) setError(improvementError(reason instanceof ApiError ? reason.code : "network_error", ru)); });
    return () => controller.abort();
  }, [active, current?.id, current?.status, current?.fixed_at, current?.fixed_publication_version, testRevision, ru]);
  useEffect(() => {
    setTurns([]); setTurnId("");
    if (!sessionId || !active || current?.status !== "fixed") return;
    const controller = new AbortController();
    api<{ turns: Turn[] }>(`testing/sessions/${sessionId}`, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setTurns(data.turns.filter(turn => turn.status === "succeeded" && turn.result?.text));
    }).catch(reason => { if (!controller.signal.aborted) setError(improvementError(reason instanceof ApiError ? reason.code : "network_error", ru)); });
    return () => controller.abort();
  }, [sessionId, active, current?.id, current?.status, testRevision, ru]);
  const text = current && draft?.id === current.id ? draft.text : "";
  const baseVersion = current && draft?.id === current.id ? draft.version : current?.version;
  const conflict = current && baseVersion !== current.version;
  async function transition(next: IssueStatus) {
    if (!current || locked.current) return;
    locked.current = true; setBusy(true); setError("");
    try {
      const value = await api<Issue>(`improvements/${current.id}`, { method: "PATCH", body: {
        version: baseVersion, status: next, note: next === "in_progress" ? "" : text,
        ...(next === "verified" ? { test_session_id: sessionId, test_request_id: turnId } : {}),
      } });
      setDetail(previous => selectedRef.current === value.id ? newerIssue(previous, value) : previous); setDraft(null); setSessionId(""); setTurnId(""); refreshList();
    } catch (reason) {
      setError(improvementError(reason instanceof ApiError ? reason.code : "network_error", ru)); refreshDetail();
    } finally { locked.current = false; setBusy(false); }
  }
  const data = list?.key === listKey ? list.data : null;
  const chosen = turns.find(turn => turn.id === turnId);
  const scopeName = (scope: string) => scope === "demo" ? (ru ? "демо" : "demo") : scope === "rule" ? (ru ? "правило" : "rule") : (ru ? "модель" : "model");
  function open(id: string | null) { selectedRef.current = id; window.history.pushState(null, "", id ? improvementHref(id) : "/dashboard#improvements"); setSelected(id); }
  return <section aria-label={ru ? "Улучшения" : "Improvement"} className="h-full overflow-y-auto p-4 text-plumo-ink md:p-6"><div className="mx-auto max-w-6xl">
    <h1 className="m-0 text-xl font-semibold">{ru ? "Улучшения" : "Improvement"}</h1>
    <p className="mb-4 mt-2 text-sm leading-6 text-plumo-muted">{ru ? "Добавляйте замечания из ответов в диалогах или тестах. Исправьте материалы или настройки, опубликуйте изменения и проверьте новый ответ." : "Report answers in conversations or tests. Correct the materials or settings, publish the changes and review a new answer."}</p>
    <div className="mb-4 flex flex-wrap gap-2"><select aria-label={ru ? "Статус замечания" : "Issue status"} value={status} onChange={event => setStatus(event.target.value)} className={control}><option value="">{ru ? "Все статусы" : "All statuses"}</option>{Object.entries(statusNames[locale]).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><button type="button" className={`${control} cursor-pointer`} onClick={() => { refreshList(); refreshDetail(); }}>{ru ? "Обновить" : "Refresh"}</button></div>
    {listError && <p role="alert" className="text-sm text-red-700">{listError}</p>}
    <div className="grid gap-4 lg:grid-cols-[320px_1fr]"><div className={selected ? "hidden lg:block" : "block"}>
      {!data ? <p role="status" className="text-sm text-plumo-muted">{ru ? "Загружаем замечания…" : "Loading issues…"}</p> : data.items.length === 0 ? <p className="rounded-xl bg-plumo-soft p-4 text-sm">{ru ? "Замечаний с таким статусом пока нет." : "No issues with this status yet."}</p> : data.items.map(item => <button key={item.id} type="button" aria-current={selected === item.id ? "true" : undefined} onClick={() => open(item.id)} className={`${control} mb-2 block w-full cursor-pointer p-3 text-left ${selected === item.id ? "!bg-plumo-soft" : ""}`}><strong className="block text-sm">{categoryNames[locale][item.category]}</strong><span className="mt-1 block text-xs text-plumo-muted">{statusNames[locale][item.status]}{item.verification ? ` · ${scopeName(item.verification.scope)}${item.verification_current ? "" : ru ? " · прежняя публикация" : " · older publication"}` : ""} · {formatTime(item.created_at, locale)}</span><span className="mt-2 block break-words text-xs leading-5">{item.note.slice(0, 200)}</span></button>)}
      <div className="mt-3 flex justify-between gap-2"><button type="button" className={`${control} cursor-pointer`} disabled={!cursors.length} onClick={() => setPages({ status, cursors: cursors.slice(0, -1) })}>{ru ? "Назад" : "Previous"}</button><button type="button" className={`${control} cursor-pointer`} disabled={!data?.next_cursor} onClick={() => { if (data?.next_cursor) setPages({ status, cursors: [...cursors, data.next_cursor] }); }}>{ru ? "Далее" : "Next"}</button></div>
    </div>
    {selected && <div className="min-w-0 rounded-xl border border-solid border-plumo-line bg-white p-4 text-sm leading-6"><button type="button" className={`${control} cursor-pointer`} onClick={() => open(null)}>{ru ? "К списку" : "Back to list"}</button>
      {error && <p role="alert" className="text-red-700">{error}</p>}
      {!current ? <p role="status">{ru ? "Загружаем карточку…" : "Loading issue…"}</p> : <>
        <h2 className="mb-0 mt-4 text-lg font-semibold">{categoryNames[locale][current.category]} · {statusNames[locale][current.status]}</h2><p className="whitespace-pre-wrap break-words">{current.note}</p>
        <p className="text-xs text-plumo-muted">{ru ? "Исходная публикация" : "Original publication"}: {current.snapshot.publication_version ?? (ru ? "версия не записана" : "version not recorded")} · {ru ? "Текущая" : "Current"}: {current.current_publication_version ?? "—"}</p>
        <details open className="rounded-lg bg-plumo-soft p-3"><summary className="cursor-pointer font-medium">{ru ? "Исходный ответ" : "Original answer"}</summary>{current.snapshot.question && <p className="whitespace-pre-wrap break-words">{ru ? "Вопрос" : "Question"}: {current.snapshot.question}</p>}<p className="whitespace-pre-wrap break-words">{current.snapshot.answer}</p><p className="text-xs text-plumo-muted">{current.snapshot.model}</p><Link href={current.snapshot.conversation_id ? conversationHref(current.snapshot.conversation_id) : testingHref(current.snapshot.test_session_id ?? "")} className="text-plumo-blue underline">{ru ? "Открыть исходный диалог или тест" : "Open source conversation or test"}</Link></details>
        {current.snapshot.source_versions.length > 0 && <div className="mt-3"><p className="mb-1 text-xs text-plumo-muted">{ru ? "Записанные версии источников; ссылки открывают текущие материалы." : "Recorded source versions; links open the current materials."}</p>{current.snapshot.source_versions.map((source, index) => <p key={`${source.id}-${index}`} className="my-1 text-xs"><Link href={knowledgeHref(source.id)} className="text-plumo-blue underline">{source.title}</Link>{source.updated_at ? ` · ${formatTime(source.updated_at, locale)}` : ""}</p>)}</div>}
        <div className="my-4 flex flex-wrap gap-3"><Link href="/dashboard#knowledge" className="text-plumo-blue underline">{ru ? "Исправить материалы" : "Correct materials"}</Link><Link href="/dashboard#settings" className="text-plumo-blue underline">{ru ? "Исправить настройки" : "Correct settings"}</Link><Link href="/dashboard#testing" className="text-plumo-blue underline">{ru ? "Открыть тестирование" : "Open testing"}</Link></div>
        {(current.status === "in_progress" || current.status === "fixed") && <label className="block">{current.status === "fixed" ? (ru ? "Ваша оценка повторного ответа" : "Your review of the new answer") : (ru ? "Что исправлено и опубликовано" : "What was corrected and published")}<textarea maxLength={2000} rows={3} value={text} disabled={busy} onChange={event => setDraft(value => ({ id: current.id, version: value?.id === current.id ? value.version : current.version, text: event.target.value }))} className={`${control} mt-1 w-full resize-y`} /></label>}
        {conflict && <p className="text-amber-800">{ru ? "Карточка обновилась. Введённый текст остался в поле." : "The card changed. Your text remains in the field."} <button type="button" onClick={() => setDraft({ id: current.id, version: current.version, text })} className="cursor-pointer border-0 bg-transparent font-[inherit] text-plumo-blue underline">{ru ? "После проверки использовать текст с новой версией" : "After review, use the text with the new version"}</button></p>}
        {current.status === "new" && <button type="button" disabled={busy} onClick={() => void transition("in_progress")} className={`${control} mt-3 cursor-pointer`}>{ru ? "Взять в работу" : "Start work"}</button>}
        {current.status === "in_progress" && <button type="button" disabled={busy || !text.trim() || !!conflict} onClick={() => void transition("fixed")} className={`${control} mt-3 cursor-pointer`}>{ru ? "Зафиксировать опубликованное исправление" : "Record published correction"}</button>}
        {current.status === "fixed" && <div className="mt-4 space-y-3"><p>{ru ? "Исправление зафиксировано для публикации" : "Correction recorded for publication"} {current.fixed_publication_version}. {current.correction_note}</p><p>{ru ? "Создайте новый тест после отметки исправления, прочитайте ответ и добавьте свою оценку." : "Create a new test after recording the correction, read its answer and add your review."}</p>
          <button type="button" className={`${control} cursor-pointer`} onClick={() => setTestRevision(value => value + 1)}>{ru ? "Обновить тесты" : "Refresh tests"}</button>
          <label className="block">{ru ? "Новый тест для исправленной версии" : "New test for the corrected version"}<select disabled={busy} value={sessionId} onChange={event => setSessionId(event.target.value)} className={`${control} mt-1 w-full`}><option value="">{ru ? "Выберите тест" : "Select test"}</option>{sessions.map(session => <option key={session.id} value={session.id}>{formatTime(session.created_at, locale)} · {session.publication_version}</option>)}</select></label>
          <label className="block">{ru ? "Успешный ответ для проверки" : "Successful answer to review"}<select disabled={busy} value={turnId} onChange={event => setTurnId(event.target.value)} className={`${control} mt-1 w-full`}><option value="">{ru ? "Выберите ответ" : "Select answer"}</option>{turns.map(turn => <option key={turn.id} value={turn.id}>{turn.text.slice(0, 100)}</option>)}</select></label>
          {chosen?.result && <div className="rounded-lg bg-plumo-soft p-3"><p className="m-0 whitespace-pre-wrap break-words">{chosen.result.text}</p><p className="mb-0 mt-2 text-xs text-plumo-muted">{chosen.result.mock ? (ru ? "Демомодель" : "Demo model") : chosen.result.model} · {ru ? "Проверено означает вашу ручную оценку этого ответа, а не общую приёмку качества." : "Verified records your review of this answer, not overall quality acceptance."}</p></div>}
          {current.current_publication_version !== current.fixed_publication_version && <p className="text-amber-800">{ru ? "Публикация снова изменилась. Верните замечание в работу и зафиксируйте новое исправление." : "Publication changed again. Reopen the issue and record the updated correction."}</p>}
          <button type="button" disabled={busy || !text.trim() || !turnId || !!conflict || current.current_publication_version !== current.fixed_publication_version} onClick={() => void transition("verified")} className={`${control} cursor-pointer`}>{ru ? "Подтвердить проверку этого ответа" : "Confirm review of this answer"}</button>
        </div>}
        {current.verification && <div className="mt-4 rounded-lg bg-plumo-soft p-3"><strong>{ru ? "Проверка публикации" : "Publication reviewed"} {current.verification.publication_version} · {current.verification.scope === "demo" ? (ru ? "демомодель" : "demo model") : current.verification.scope === "rule" ? (ru ? "правило" : "rule") : (ru ? "модель" : "model")}</strong><p className="whitespace-pre-wrap break-words">{current.verification.note}</p><Link href={testingHref(current.verification.test_session_id)} className="text-plumo-blue underline">{ru ? "Открыть подтверждающий тест" : "Open verification test"}</Link>{!current.verification_current && <p className="mb-0 text-amber-800">{ru ? "Эта проверка относится к прежней публикации." : "This review belongs to an older publication."}</p>}</div>}
        {(current.status === "fixed" || current.status === "verified") && <button type="button" disabled={busy} onClick={() => void transition("in_progress")} className={`${control} mt-4 cursor-pointer`}>{ru ? "Вернуть в работу" : "Reopen"}</button>}
        <details className="mt-5"><summary className="cursor-pointer font-medium">{ru ? "История изменений" : "Change history"}</summary>{current.history.map((event, index) => <div key={index} className="mt-3 border-0 border-t border-solid border-plumo-line pt-2 text-xs"><p className="m-0">{statusNames[locale][event.status]} · {formatTime(event.at, locale)}</p>{event.note && <p className="mb-0 mt-1 whitespace-pre-wrap break-words">{event.note}</p>}{event.verification && <Link href={testingHref(event.verification.test_session_id)} className="text-plumo-blue underline">{ru ? "Тест для публикации" : "Test for publication"} {event.verification.publication_version} · {scopeName(event.verification.scope)}</Link>}</div>)}</details>
      </>}
    </div>}
    </div>
  </div></section>;
}
