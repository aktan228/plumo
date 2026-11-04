"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";

type Revision = { publication_version: number; settings: Record<string, string>; published_at: string | null; captured_at: string };
type History = { publication_version: number | null; settings: Record<string, string>; items: Revision[]; next_before: number | null };
const button = "min-h-10 rounded-lg border border-solid border-plumo-line bg-white px-4 py-2 text-sm focus-visible:outline-2 focus-visible:outline-plumo-blue disabled:opacity-50";
const names: Record<string, [string, string]> = { purpose: ["Задача", "Purpose"], goal: ["Цель", "Goal"], greeting: ["Приветствие", "Greeting"], qualificationPrompt: ["Что выяснить", "What to clarify"], openingQuestion: ["Первый вопрос", "Opening question"], handoffRules: ["Условия передачи", "Handoff conditions"], handoffKeywords: ["Фразы передачи", "Handoff phrases"], fallback: ["Нет ответа", "Missing answer"] };

export function ScenarioHistory({ active, published, ru }: { active: boolean; published: boolean; ru: boolean }) {
  const [data, setData] = useState<History | null>(null);
  const [before, setBefore] = useState<number | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setLoading(true); setFailed(false);
    void api<History>(`scenarios${before === null ? "" : `?before=${before}`}`, { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) setData(value);
    }).catch(() => { if (!controller.signal.aborted) setFailed(true); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [active, published, before, refresh]);
  const fields = (settings: Record<string, string>) => <dl className="grid gap-3 text-sm">{Object.entries(names).map(([key, label]) => <div key={key}><dt className="text-plumo-muted">{label[ru ? 0 : 1]}</dt><dd className="m-0 mt-1 whitespace-pre-wrap break-words">{settings[key] || "—"}</dd></div>)}</dl>;
  return <section className="rounded-2xl border border-solid border-plumo-line bg-white p-5">
    <h3 className="m-0 text-base font-semibold">{ru ? "Опубликованный сценарий и история" : "Published scenario and history"}</h3>
    <p className="text-sm leading-6 text-plumo-muted">{ru ? "Черновик выше не меняет ответы до общей публикации. Старые тесты сохраняют номер своей публикации; после изменений начните новый тест. История ведётся с DB-11, прежние версии восстановить нельзя." : "The draft above does not change replies until shared publication. Old tests keep their publication number; start a new test after changes. History begins with DB-11; earlier revisions cannot be reconstructed."}</p>
    <button type="button" className={button} disabled={loading} onClick={() => { setBefore(null); setRefresh(value => value + 1); }}>{ru ? "Обновить" : "Refresh"}</button>
    {loading && <p role="status" className="text-sm">{ru ? "Загрузка…" : "Loading…"}</p>}
    {failed ? <p role="alert" className="text-sm">{ru ? "Не удалось загрузить историю. Повторите обновление." : "Could not load history. Refresh to retry."}</p> : !loading && data && <>
      <details className="mt-4"><summary className="cursor-pointer text-sm">{ru ? "Действующая публикация" : "Current publication"}: {data.publication_version ?? "—"}</summary>{data.publication_version !== null && fields(data.settings)}</details>
      {data.items.map(item => <details key={item.publication_version} className="mt-4"><summary className="cursor-pointer text-sm">v{item.publication_version} · {item.published_at ? new Date(item.published_at).toLocaleString(ru ? "ru-RU" : "en-GB", { timeZone: "Asia/Bishkek" }) : (ru ? "время старой публикации неизвестно" : "original publication time unknown")}</summary>{fields(item.settings)}</details>)}
      <div className="mt-4 flex gap-2">{before !== null && <button className={button} type="button" onClick={() => setBefore(null)}>{ru ? "К последним" : "Latest"}</button>}{data.next_before !== null && <button className={button} type="button" onClick={() => setBefore(data.next_before)}>{ru ? "Более ранние" : "Older"}</button>}</div>
    </>}
  </section>;
}
