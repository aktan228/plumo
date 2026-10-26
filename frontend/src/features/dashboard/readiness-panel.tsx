"use client";
import Link from "next/link";
import { useCallback, useState } from "react";
import { api, ApiError, goToLogin } from "@/lib/api/client";
import { useLanguage } from "@/lib/i18n";
import { usePolling } from "@/lib/api/use-polling";
import { DashboardIcon } from "./dashboard-icon";

type Item = { key: "business" | "materials" | "test" | "channel"; status: string; ready: boolean; count?: number };
type Readiness = { items: Item[]; completed: number; total: number; ready: boolean; running: boolean };
const action = "cursor-pointer border-0 bg-transparent p-0 font-[inherit] text-[11px] text-plumo-blue hover:underline";

export function ReadinessPanel({ onTesting, onIntegrations }: { onTesting: () => void; onIntegrations: () => void }) {
  const { locale } = useLanguage();
  const ru = locale === "ru";
  const [data, setData] = useState<Readiness | null>(null);
  const [error, setError] = useState(false);
  const load = useCallback(async (signal?: AbortSignal) => {
    try { setData(await api<Readiness>("dashboard/readiness", { signal })); setError(false); }
    catch (e) { if (e instanceof ApiError && e.unauthenticated) goToLogin(); if (!(e instanceof DOMException && e.name === "AbortError")) setError(true); throw e; }
  }, []);
  const refresh = usePolling(load, 15000, "readiness");
  const names = ru ? { business:"Бизнес", materials:"Материалы", test:"Тест агента", channel:"Канал" } : { business:"Business", materials:"Materials", test:"Agent test", channel:"Channel" };
  const labels: Record<string, string> = ru ? { ready:"Готово", pending:"Нужно настроить", demo:"Проверено на демомодели", started:"Проверьте ответ модели", connected:"Нужно проверить доставку", running:"Ответы включены" } : { ready:"Ready", pending:"Setup needed", demo:"Tested with demo model", started:"Test a model reply", connected:"Verify delivery", running:"Replies enabled" };
  const icons = { business:"settings", materials:"book", test:"testing", channel:"integrations" } as const;
  return <section aria-label={ru ? "Готовность к запуску" : "Launch readiness"} className="shrink-0 border-0 border-b border-solid border-plumo-line bg-white px-3 py-3 md:px-4">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h2 className="m-0 text-[13px] font-medium">{ru ? "Готовность к запуску" : "Launch readiness"}</h2><span className="text-[11px] text-plumo-muted" role="status">{data ? `${data.completed}/${data.total}` : (ru ? "Проверяем…" : "Checking…")}{data?.ready ? (ru ? " · Всё готово к запуску" : " · Ready to launch") : ""}</span></div>
    {error && <p role="alert" className="m-0 text-[12px] text-plumo-muted">{ru ? "Не удалось проверить готовность." : "Could not check readiness."} <button type="button" className={action} onClick={refresh}>{ru ? "Повторить" : "Retry"}</button></p>}
    {data && <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">{data.items.map(item => <div key={item.key} className="min-w-0 rounded-xl border border-solid border-plumo-line px-3 py-2.5"><div className="flex items-center gap-2 text-[12px]"><DashboardIcon name={icons[item.key]} size={15} /><span>{names[item.key]}</span>{item.ready && <span aria-label={ru ? "Готово" : "Ready"} className="ml-auto text-emerald-700"><DashboardIcon name="check" size={13} /></span>}</div><p className="mb-2 mt-2 text-[11px] leading-4 text-plumo-muted">{labels[item.status] ?? item.status}{item.key === "materials" && item.count ? ` · ${item.count}` : ""}</p>{item.key === "business" || item.key === "materials" ? <Link href="/create/wizard" className={action}>{ru ? (item.key === "materials" ? "Добавить материалы" : "Настроить") : (item.key === "materials" ? "Add materials" : "Set up")}</Link> : <button type="button" className={action} onClick={item.key === "test" ? onTesting : onIntegrations}>{ru ? (item.key === "test" ? "Открыть тест" : item.ready ? "Открыть канал" : "Подключить канал") : (item.key === "test" ? "Open test" : item.ready ? "Open channel" : "Connect channel")}</button>}</div>)}</div>}
  </section>;
}
