"use client";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, api } from "@/lib/api/client";
import { useLanguage } from "@/lib/i18n";
import { improvementHref } from "./navigation";
import { categories, categoryNames, improvementError, type AnswerSource, type Category } from "./improvement-model";

export function ReportAnswer({ source }: { source: AnswerSource }) {
  const { locale } = useLanguage();
  const ru = locale === "ru";
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<Category>("incorrect_fact");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<string | null>(null);
  const attempt = useRef<(AnswerSource & { id: string; category: Category; note: string }) | null>(null);
  const locked = useRef(false);
  useEffect(() => {
    if (!open || !note.trim()) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [open, note]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (locked.current || !note.trim()) return;
    locked.current = true; setBusy(true); setError("");
    attempt.current ??= { ...source, id: crypto.randomUUID(), category, note: note.trim() };
    try {
      const result = await api<{ id: string }>("improvements", { method: "POST", body: attempt.current });
      setCreated(result.id); setOpen(false); setNote(""); attempt.current = null;
    } catch (reason) {
      setError(improvementError(reason instanceof ApiError ? reason.code : "network_error", ru));
      if (reason instanceof ApiError && reason.status >= 400 && reason.status < 500 && ![408, 429].includes(reason.status)) attempt.current = null;
    } finally { locked.current = false; setBusy(false); }
  }
  const disabled = busy || attempt.current !== null;
  const control = "rounded-lg border border-solid border-plumo-line bg-white px-2 py-1.5 font-[inherit] text-xs text-plumo-ink focus-visible:outline-2 focus-visible:outline-plumo-blue disabled:opacity-50";
  return <div className="mt-2 text-left text-xs">
    {created && <p role="status" className="m-0"><Link href={improvementHref(created)} className="text-plumo-blue underline">{ru ? "Замечание сохранено — открыть" : "Issue saved — open"}</Link></p>}
    {!open ? <button type="button" onClick={() => { setOpen(true); setError(""); }} className="cursor-pointer rounded border-0 bg-transparent p-1 font-[inherit] text-[11px] text-plumo-blue hover:underline focus-visible:outline-2 focus-visible:outline-plumo-blue">{ru ? "Добавить замечание" : "Report this answer"}</button>
      : <form onSubmit={submit} className="space-y-2 rounded-lg border border-solid border-plumo-line bg-white p-3">
        <label className="block">{ru ? "Тип замечания" : "Category"}<select disabled={disabled} value={category} onChange={event => setCategory(event.target.value as Category)} className={`${control} mt-1 w-full`}>{categories.map(value => <option key={value} value={value}>{categoryNames[locale][value]}</option>)}</select></label>
        <label className="block">{ru ? "Что нужно исправить" : "What needs correction"}<textarea required disabled={disabled} maxLength={2000} rows={3} value={note} onChange={event => setNote(event.target.value)} className={`${control} mt-1 w-full resize-y`} /></label>
        {error && <p role="alert" className="m-0 text-red-700">{error}</p>}
        <div className="flex flex-wrap gap-2"><button type="submit" disabled={busy || !note.trim()} className={`${control} cursor-pointer`}>{busy ? (ru ? "Сохраняем…" : "Saving…") : attempt.current ? (ru ? "Повторить сохранение" : "Retry save") : (ru ? "Сохранить замечание" : "Save issue")}</button><button type="button" disabled={disabled} onClick={() => setOpen(false)} className={`${control} cursor-pointer`}>{ru ? "Отмена" : "Cancel"}</button></div>
      </form>}
  </div>;
}
