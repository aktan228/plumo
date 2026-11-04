"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useLanguage } from "@/lib/i18n";
import { api, ApiError } from "@/lib/api/client";
import type { WizardStorage } from "@/features/create-agent/use-wizard-storage";
import { MAX_SOURCE_BYTES, MAX_SOURCES, sourceUrl, type Source } from "@/features/create-agent/wizard-model";
import { formatTime } from "./dialogue-model";
import { materialIssue, updateMaterial } from "./knowledge-model";

type Published = { id: string; title: string; content: string; active: boolean; updated_at: string; metadata: { source_title?: string; origin?: string } };
const inputClass = "w-full rounded-lg border border-solid border-plumo-line bg-white px-3 py-2.5 font-[inherit] text-sm text-plumo-ink focus:outline-2 focus:outline-plumo-blue";
const button = "inline-flex min-h-10 cursor-pointer items-center justify-center rounded-lg border border-solid border-plumo-line bg-white px-4 py-2 text-sm text-plumo-ink hover:bg-plumo-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-default disabled:opacity-50";
const primary = `${button} border-plumo-blue bg-plumo-blue text-white hover:bg-plumo-blue/90`;

export function KnowledgeBase({ active, storage, onEditingChange }: { active: boolean; storage: WizardStorage; onEditingChange: (editing: boolean) => void }) {
  const { locale } = useLanguage();
  const ru = locale === "ru";
  const [query, setQuery] = useState("");
  const [editor, setEditor] = useState<Source | null>(null);
  const [baseline, setBaseline] = useState("");
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const [confirmPublish, setConfirmPublish] = useState(false);
  const [published, setPublished] = useState<Published[] | null>(null);
  const [publishedError, setPublishedError] = useState(false);
  const [sourceMissing, setSourceMissing] = useState(false);
  const [revision, setRevision] = useState(0);
  const fileEpoch = useRef(0);
  const editorRef = useRef<HTMLHeadingElement>(null);
  const sources = storage.snapshot.sources;
  const blocked = !storage.ready || storage.finishing || reading || storage.status === "conflict" || storage.status === "expired";
  const editorDirty = editor !== null && JSON.stringify(editor) !== baseline;
  const editing = editor !== null;
  useEffect(() => { onEditingChange(editing); }, [editing, onEditingChange]);
  const c = ru ? {
    title: "База знаний", intro: "Материалы, на которые агент опирается в ответах клиентам.", add: "Добавить материал", search: "Поиск по названию и содержимому", empty: "Материалов пока нет. Добавьте текст, FAQ или файл TXT/MD.", noMatches: "Ничего не найдено. Измените поиск.",
    edit: "Открыть", off: "Отключён в черновике", draft: "Черновик", live: "Опубликовано", reference: "Ссылка · содержимое не загружается", enable: "Включить", disable: "Отключить", saving: "Сохраняем…", saved: "Черновик сохранён", changed: "Есть изменения", publish: "Опубликовать", cancel: "Отмена", save: "Сохранить в черновик", name: "Название", content: "Текст материала", question: "Вопрос", answer: "Ответ", kind: "Тип материала", loading: "Загружаем…", retry: "Повторить", restore: "Загрузить актуальную версию", download: "Скачать свой черновик", setup: "Настройки бизнеса", test: "Проверить ответы",
    shared: "Материалы и настройки используют общий черновик с мастером. Сохранение черновика не меняет ответы агента до публикации.", confirm: "Будут опубликованы все материалы и настройки из общего черновика, включая изменения в мастере. Отключённые материалы перестанут использоваться после публикации. Проверьте настройки перед подтверждением.", confirmAction: "Опубликовать общий черновик", conflict: "Черновик изменён в другой вкладке. Ваш ввод сохранён на этом экране. Скачайте его перед загрузкой актуальной версии и перенесите нужные изменения.", expired: "Сессия завершена. Скачайте свой черновик перед повторным входом.", failed: "Не удалось сохранить или опубликовать. Ввод сохранён на этом экране. Проверьте соединение и повторите.", invalidSetup: "Заполните настройки бизнеса и агента в мастере. Незаконченный ввод материала в мастере также нужно завершить.",
    published: "Что сейчас доступно агенту", publishedHint: "Здесь показаны действующие фрагменты, включая материалы, добавленные командой. Исходные материалы мастера редактируются выше.", unavailable: "Не удалось загрузить опубликованные материалы.", noPublished: "Опубликованных материалов нет.", afterPublish: "После публикации начните новый тест и проверьте факты и цены.", file: "TXT или MD · UTF-8 · до 100 КБ", fileError: "Выберите TXT/MD до 100 КБ в UTF-8 без нулевых символов.", leaveEditor: "Сначала сохраните или отмените редактирование материала.", limits: "До 10 источников, до 100 КБ на источник и до 200 КБ суммарно.",
  } : {
    title: "Knowledge Base", intro: "Materials your agent uses when replying to customers.", add: "Add material", search: "Search titles and content", empty: "No materials yet. Add text, Q&A or a TXT/MD file.", noMatches: "No results. Change your search.", edit: "Open", off: "Disabled in draft", draft: "Draft", live: "Published", reference: "Link · content is not imported", enable: "Enable", disable: "Disable", saving: "Saving…", saved: "Draft saved", changed: "Changes pending", publish: "Publish", cancel: "Cancel", save: "Save to draft", name: "Title", content: "Material text", question: "Question", answer: "Answer", kind: "Material type", loading: "Loading…", retry: "Retry", restore: "Load current version", download: "Download your draft", setup: "Business settings", test: "Test replies",
    shared: "Materials and settings share the wizard draft. Saving a draft does not change agent replies until publication.", confirm: "All materials and settings in the shared draft will be published, including wizard changes. Disabled materials will stop being used after publication. Review settings before confirming.", confirmAction: "Publish shared draft", conflict: "Another tab changed this draft. Your input remains on this screen. Download it before loading the current version, then reapply the changes you need.", expired: "Your session ended. Download your draft before signing in again.", failed: "Could not save or publish. Your input remains on this screen. Check the connection and retry.", invalidSetup: "Complete business and agent settings in the wizard. Finish any pending material input in the wizard as well.",
    published: "Currently available to the agent", publishedHint: "Active published fragments, including materials added by the team. Edit wizard source materials above.", unavailable: "Could not load published materials.", noPublished: "No published materials.", afterPublish: "After publishing, start a new test and check facts and prices.", file: "TXT or MD · UTF-8 · up to 100 KB", fileError: "Choose a UTF-8 TXT/MD file up to 100 KB without NUL characters.", leaveEditor: "Save or cancel material editing first.", limits: "Up to 10 sources, 100 KB per source and 200 KB combined.",
  };
  const kinds: Record<Source["kind"], string> = ru ? { text: "Текст", faq: "Вопрос–ответ", file: "Файл", website: "Сайт", instagram: "Instagram" } : { text: "Text", faq: "Q&A", file: "File", website: "Website", instagram: "Instagram" };

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    void api<Published[]>("knowledge", { signal: controller.signal }).then(data => {
      setPublished(data.filter(item => item.active)); setPublishedError(false);
    }).catch(() => { if (!controller.signal.aborted) setPublishedError(true); });
    return () => controller.abort();
  }, [active, revision, storage.completed]);

  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => { if (editorDirty) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [editorDirty]);

  useEffect(() => {
    if (!active || !published) return;
    const id = new URLSearchParams(window.location.search).get("source");
    setSourceMissing(!!id && !published.some(item => item.id === id));
    if (!id || !published.some(item => item.id === id)) return;
    const element = document.getElementById(`knowledge-${id}`);
    if (element instanceof HTMLDetailsElement) {
      element.open = true;
      element.scrollIntoView({ block: "center" });
      element.querySelector("summary")?.focus();
    }
  }, [active, published]);

  function open(source?: Source) {
    const next: Source = source ? { ...source } : { id: crypto.randomUUID(), kind: "text", title: "", content: "" };
    setEditor(next); setBaseline(JSON.stringify(next)); setError(""); setConfirmPublish(false);
    requestAnimationFrame(() => editorRef.current?.focus());
  }

  function closeEditor() { fileEpoch.current += 1; setEditor(null); setReading(false); setError(""); }

  async function readFile(file?: File) {
    if (!file || !editor) return;
    const epoch = ++fileEpoch.current;
    setReading(true); setError("");
    try {
      if (!/\.(txt|md)$/i.test(file.name) || file.size > MAX_SOURCE_BYTES) throw new Error();
      const content = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
      if (!content.trim() || content.includes("\0")) throw new Error();
      if (epoch === fileEpoch.current) setEditor({ ...editor, kind: "file", title: file.name.slice(0, 300), content });
    } catch { if (epoch === fileEpoch.current) setError(c.fileError); }
    finally { if (epoch === fileEpoch.current) setReading(false); }
  }

  function saveEditor() {
    if (!editor) return;
    const content = editor.kind === "website" || editor.kind === "instagram" ? sourceUrl(editor.content.trim(), editor.kind === "instagram") ?? editor.content.trim() : editor.content.trim();
    const cleaned = { ...editor, title: editor.title.trim(), content, ...(editor.question !== undefined ? { question: editor.question.trim() } : {}) };
    const issue = materialIssue(cleaned, sources);
    if (issue) {
      const messages = ru ? { title: "Введите название до 300 символов.", content: "Добавьте текст без нулевых символов.", question: "Введите вопрос до 300 символов.", url: "Введите корректную ссылку.", limits: c.limits } : { title: "Enter a title up to 300 characters.", content: "Add text without NUL characters.", question: "Enter a question up to 300 characters.", url: "Enter a valid URL.", limits: c.limits };
      setError(messages[issue]); return;
    }
    storage.change(previous => ({ ...previous, sources: updateMaterial(previous.sources, cleaned) }));
    closeEditor(); setConfirmPublish(false);
  }

  function download() {
    const blob = new Blob([JSON.stringify({ ...storage.snapshot, unsavedMaterial: editor }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
    anchor.href = url; anchor.download = "plumo-knowledge-draft.json"; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const visible = sources.filter(source => `${source.title} ${source.content} ${source.question ?? ""}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const statusText = storage.status === "saving" ? c.saving : storage.status === "dirty" ? c.changed : storage.completed ? c.live : c.saved;
  const failureText = storage.status === "conflict" ? c.conflict : storage.status === "expired" ? c.expired : storage.failure === "invalid_message" ? c.invalidSetup : c.failed;

  return <section className="h-full overflow-y-auto p-4 md:p-6">
    <div className="mx-auto max-w-[1100px]">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="m-0 text-2xl font-semibold">{c.title}</h2><p className="mb-0 mt-2 text-sm text-plumo-muted">{c.intro}</p></div><button type="button" className={primary} disabled={blocked || editor !== null || sources.length >= MAX_SOURCES} onClick={() => open()}>{c.add}</button></div>
      <p className="my-4 text-sm leading-6 text-plumo-muted">{c.shared} {c.limits}</p>
      <div className="mb-4 flex flex-wrap items-center gap-3"><span role="status" className="text-xs text-plumo-muted">{storage.ready ? statusText : c.loading}</span><a href="#settings" className="text-sm text-plumo-blue underline">{c.setup}</a><a href="#testing" className="text-sm text-plumo-blue underline">{c.test}</a><button type="button" className={`${button} ml-auto`} disabled={blocked || !sources.length || editor !== null || storage.completed} onClick={() => setConfirmPublish(true)}>{c.publish}</button></div>
      {["error", "conflict", "expired"].includes(storage.status) && <div role="alert" className="mb-4 rounded-xl border border-solid border-plumo-line bg-plumo-soft p-4 text-sm leading-6"><p className="m-0">{failureText}</p><div className="mt-3 flex flex-wrap gap-2"><button type="button" className={button} onClick={download}>{c.download}</button>{storage.status === "error" ? <button type="button" className={button} onClick={() => { if (storage.ready) void storage.flush(); else void storage.reload(); }}>{c.retry}</button> : storage.status === "conflict" ? <button type="button" className={button} onClick={() => { closeEditor(); void storage.reload(); }}>{c.restore}</button> : <Link href="/login?next=/dashboard%23knowledge" className={button}>{ru ? "Войти" : "Sign in"}</Link>}</div></div>}
      {confirmPublish && <div role="group" aria-label={c.publish} className="mb-4 rounded-xl border border-solid border-plumo-blue/30 bg-plumo-soft p-4 text-sm leading-6"><p className="m-0">{c.confirm}</p><div className="mt-3 flex flex-wrap gap-2"><button type="button" className={primary} disabled={blocked || editor !== null} onClick={async () => { if (await storage.complete()) { setConfirmPublish(false); setRevision(value => value + 1); } }}>{storage.finishing ? c.saving : c.confirmAction}</button><button type="button" className={button} disabled={storage.finishing} onClick={() => setConfirmPublish(false)}>{c.cancel}</button></div></div>}
      {editor && <div className="mb-5 rounded-2xl border border-solid border-plumo-blue/30 bg-white p-5">
        <h3 ref={editorRef} tabIndex={-1} className="m-0 text-base font-semibold focus:outline-none">{sources.some(source => source.id === editor.id) ? c.edit : c.add}</h3>
        <div className="mt-4 grid gap-4">
          <label className="grid gap-2 text-sm">{c.kind}<select className={inputClass} value={editor.kind} disabled={blocked || editor.kind === "website" || editor.kind === "instagram"} onChange={event => setEditor({ ...editor, kind: event.target.value as Source["kind"], question: undefined })}>{(editor.kind === "website" || editor.kind === "instagram" ? [editor.kind] : ["text", "faq", "file"] as const).map(kind => <option key={kind} value={kind}>{kinds[kind]}</option>)}</select></label>
          <label className="grid gap-2 text-sm">{c.name}<input className={inputClass} value={editor.title} maxLength={300} disabled={blocked} onChange={event => setEditor({ ...editor, title: event.target.value })} /></label>
          {editor.kind === "file" && <label className="grid gap-2 text-sm">{c.file}<input type="file" accept=".txt,.md,text/plain,text/markdown" disabled={blocked} onChange={event => { void readFile(event.target.files?.[0]); event.target.value = ""; }} /></label>}
          {editor.kind === "faq" && <label className="grid gap-2 text-sm">{c.question}<input className={inputClass} value={editor.question ?? ""} maxLength={300} disabled={blocked} onChange={event => setEditor({ ...editor, question: event.target.value })} /></label>}
          <label className="grid gap-2 text-sm">{editor.kind === "faq" ? c.answer : c.content}<textarea className={inputClass} rows={8} value={editor.content} maxLength={100000} disabled={blocked} onChange={event => setEditor({ ...editor, content: event.target.value })} /></label>
          {(editor.kind === "website" || editor.kind === "instagram") && <p className="m-0 text-sm text-plumo-muted">{c.reference}</p>}
          {error && <p role="alert" className="m-0 text-sm text-red-700">{error}</p>}
          <div className="flex flex-wrap gap-2"><button type="button" className={primary} disabled={blocked} onClick={saveEditor}>{reading ? c.loading : c.save}</button><button type="button" className={button} disabled={reading} onClick={closeEditor}>{c.cancel}</button>{editorDirty && <button type="button" className={button} onClick={download}>{c.download}</button>}</div>
        </div>
      </div>}
      <label className="mb-4 grid gap-2 text-sm">{c.search}<input type="search" className={inputClass} value={query} onChange={event => setQuery(event.target.value)} /></label>
      {storage.ready && visible.length === 0 && <p className="rounded-xl border border-dashed border-plumo-line p-6 text-sm text-plumo-muted">{sources.length ? c.noMatches : c.empty}</p>}
      <ul className="m-0 grid list-none gap-3 p-0">{visible.map(source => <li key={source.id} className="rounded-xl border border-solid border-plumo-line bg-white p-4"><div className="flex flex-wrap items-center gap-2"><h3 className="m-0 min-w-0 break-words text-sm font-semibold">{source.title}</h3><span className="rounded bg-plumo-soft px-2 py-1 text-xs text-plumo-muted">{kinds[source.kind]}</span><span className="text-xs text-plumo-muted">{source.enabled === false ? c.off : source.kind === "website" || source.kind === "instagram" ? c.reference : storage.completed ? c.live : c.draft}</span></div><p className="mb-3 mt-2 line-clamp-2 whitespace-pre-wrap break-words text-sm leading-6 text-plumo-muted">{source.question ? `${source.question}\n` : ""}{source.content}</p><div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={blocked || editor !== null} onClick={() => open(source)}>{c.edit}</button><button type="button" className={button} disabled={blocked || editor !== null} onClick={() => { storage.change(previous => ({ ...previous, sources: previous.sources.map(item => item.id === source.id ? { ...item, enabled: item.enabled === false } : item) })); setConfirmPublish(false); }}>{source.enabled === false ? c.enable : c.disable}</button></div></li>)}</ul>
      {sourceMissing && <p role="status" className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">{ru ? "Источник из этого теста недоступен среди текущих материалов. Он мог быть отключён или заменён после публикации." : "This test source is not available in the current materials. It may have been disabled or replaced after publication."}</p>}
      <div className="mt-8 border-0 border-t border-solid border-plumo-line pt-5"><h3 className="m-0 text-lg font-semibold">{c.published}</h3><p className="mb-4 mt-2 text-sm leading-6 text-plumo-muted">{c.publishedHint} {c.afterPublish}</p>{publishedError ? <p role="alert" className="text-sm">{c.unavailable} <button type="button" className={button} onClick={() => setRevision(value => value + 1)}>{c.retry}</button></p> : published === null ? <p className="text-sm text-plumo-muted">{c.loading}</p> : published.length === 0 ? <p className="text-sm text-plumo-muted">{c.noPublished}</p> : <div className="grid gap-2">{published.map(item => <details key={item.id} id={`knowledge-${item.id}`} className="rounded-lg border border-solid border-plumo-line bg-white p-3"><summary className="cursor-pointer break-words text-sm">{item.metadata.source_title ?? item.title} · {formatTime(item.updated_at, locale)}</summary><p className="mb-0 whitespace-pre-wrap break-words text-sm leading-6 text-plumo-muted">{item.content}</p></details>)}</div>}</div>
    </div>
  </section>;
}
