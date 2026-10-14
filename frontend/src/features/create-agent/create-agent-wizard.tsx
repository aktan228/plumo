"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import { LanguageSwitch, useLanguage } from "@/lib/i18n";
import { DemoChoice } from "@/components/landing/demo-choice";
import { DemoContactForm } from "@/components/landing/demo-contact-form";
import { pricingRequestLabel, type PricingRequest } from "@/components/landing/pricing";
import { demoReply, emptyDraft, example, makeScript, MAX_SOURCE_BYTES, sourceFits, sourceUrl, type AgentDraft, type Source } from "./wizard-model";
import { wizardCopy } from "./wizard-copy";

const input = "w-full min-w-0 rounded-xl border border-solid border-plumo-line bg-white px-3.5 py-3 font-[inherit] text-[16px] leading-6 text-plumo-ink placeholder:text-plumo-muted/65 focus:border-plumo-blue focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue";
const primary = "inline-flex min-h-12 cursor-pointer items-center justify-center gap-3 rounded-xl border border-solid border-plumo-ink bg-plumo-ink px-5 py-3 font-[inherit] text-[14px] font-medium text-white transition-opacity hover:opacity-85 disabled:cursor-wait disabled:opacity-50";
const secondary = "inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-xl border border-solid border-plumo-line bg-white px-4 py-2.5 font-[inherit] text-[13px] text-plumo-ink hover:bg-plumo-line/25 disabled:cursor-wait disabled:opacity-50";
const label = "flex min-w-0 flex-col gap-2 text-[13px] leading-5";
type Message = { role: "user" | "agent"; text: string; source?: string };
type Kind = Source["kind"];

function Mark({ draft, size = 48 }: { draft: AgentDraft; size?: number }) {
  return <span className="inline-flex shrink-0 items-center justify-center overflow-hidden rounded-2xl text-white" style={{ width: size, height: size, backgroundColor: draft.color }}>
    {draft.logo ? <img src={draft.logo} alt="" width={size} height={size} className="h-full w-full object-cover" /> : <svg aria-hidden="true" width={size / 2} height={size / 2} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M6 20V4h6a6 6 0 0 1 0 12H6" /><path d="m14 6 3 3-3 3" /></svg>}
  </span>;
}

function Field({ title, children }: { title: string; children: ReactNode }) {
  return <label className={label}>{title}{children}</label>;
}

export function CreateAgentWizard() {
  const { locale, t } = useLanguage();
  const c = wizardCopy[locale];
  const reduced = useReducedMotion();
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<AgentDraft>({ ...emptyDraft });
  const [sources, setSources] = useState<Source[]>([]);
  const [kind, setKind] = useState<Kind>("website");
  const [value, setValue] = useState("");
  const [question, setQuestion] = useState("");
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [handedOff, setHandedOff] = useState(false);
  const [channel, setChannel] = useState(0);
  const [contact, setContact] = useState(false);
  const [mailReady, setMailReady] = useState(false);
  const [downloaded, setDownloaded] = useState(false);
  const [pricing, setPricing] = useState<PricingRequest | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const initialStep = useRef(true);
  const baseScript = makeScript(draft);
  const greeting = draft.greeting || baseScript.greeting;
  const faqs = sources.filter(source => source.kind === "faq");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const choice = params.get("plan");
    const volume = Number(params.get("volume"));
    if (["start", "business", "custom", "demo"].includes(choice ?? "") && volume >= 1000 && volume <= 10000 && volume % 500 === 0) {
      setPricing({ choice: choice as PricingRequest["choice"], volume, billing: params.get("billing") === "quarter" ? "quarter" : "month", voice: params.get("voice") === "true" });
    }
  }, []);

  useEffect(() => {
    if (initialStep.current) { initialStep.current = false; return; }
    heading.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [step]);

  useEffect(() => {
    if (transcript.current) transcript.current.scrollTop = transcript.current.scrollHeight;
  }, [messages, step]);

  function update<K extends keyof AgentDraft>(key: K, next: AgentDraft[K]) {
    setDraft(previous => ({ ...previous, [key]: next }));
    setDownloaded(false);
  }

  function append(source: Source) {
    if (!sourceFits(sources, source)) { setError(c.limitError); return false; }
    setSources(previous => [...previous, source]);
    setValue(""); setQuestion(""); setError(""); setDownloaded(false);
    return true;
  }

  function addSource() {
    if (kind === "website" || kind === "instagram") {
      const url = sourceUrl(value, kind === "instagram");
      if (!url) { setError(c.urlError); return false; }
      return append({ id: crypto.randomUUID(), kind, title: new URL(url).hostname, content: url });
    }
    if (!value.trim() || (kind === "faq" && !question.trim())) { setError(c.textError); return false; }
    return append({ id: crypto.randomUUID(), kind, title: kind === "faq" ? question.trim() : c.material, content: value.trim(), ...(kind === "faq" ? { question: question.trim() } : {}) });
  }

  async function readFile(file?: File) {
    if (!file) return;
    setError("");
    if (!/\.(txt|md)$/i.test(file.name) || file.size > MAX_SOURCE_BYTES) { setError(c.fileError); return; }
    setReading(true);
    try {
      const content = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
      if (!content.trim() || content.includes("\0")) throw new Error("Invalid text");
      append({ id: crypto.randomUUID(), kind: "file", title: file.name, content });
    } catch { setError(c.fileError); }
    finally { setReading(false); }
  }

  async function readLogo(file?: File) {
    if (!file) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 1_000_000) { setError(c.logoError); return; }
    setReading(true); setError("");
    try {
      const url = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
      await new Promise<void>((resolve, reject) => { const img = new window.Image(); img.onload = () => resolve(); img.onerror = reject; img.src = url; });
      setDraft(previous => ({ ...previous, logo: url, logoName: file.name }));
      setDownloaded(false);
    } catch { setError(c.logoError); }
    finally { setReading(false); }
  }

  function next(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (reading) return;
    if (step === 0) {
      const pending = kind !== "file" && (value.trim() || question.trim());
      if (pending && !addSource()) return;
      if (!pending && !sources.length) { setError(c.sourceRequired); return; }
    }
    if (step === 1 && (!draft.company.trim() || !draft.description.trim())) { setError(c.required); return; }
    if (step === 3) {
      if (!draft.name.trim()) { setError(c.required); return; }
      setDraft(previous => ({ ...previous, greeting: previous.greeting || baseScript.greeting, goal: previous.goal || baseScript.goal, fallback: previous.fallback || baseScript.fallback }));
    }
    if (step === 4) {
      if (![draft.greeting, draft.goal, draft.fallback].every(v => v.trim())) { setError(c.required); return; }
      setMessages([]); setHandedOff(false); setChatInput("");
    }
    setStep(previous => Math.min(5, previous + 1));
  }

  function useExample() {
    const sample = example(locale);
    setSources(sample.sources); setDraft(sample.draft); setValue(""); setQuestion(""); setError(""); setDownloaded(false);
    setStep(1);
  }

  function send(text: string) {
    if (!text.trim() || handedOff) return;
    const response = demoReply(text.trim(), draft, sources);
    setMessages(previous => [...previous, { role: "user" as const, text: text.trim() }, { role: "agent" as const, text: response.text, source: response.source }].slice(-40));
    if (response.handoff) setHandedOff(true);
    setChatInput("");
  }

  function download() {
    const { logo: _logo, ...settings } = draft;
    const config = { version: 1, mode: "scripted-demo", settings: { ...settings, ...{ greeting, goal: draft.goal || baseScript.goal, fallback: draft.fallback || baseScript.fallback } }, sources, requestedChannel: c.channels[channel], pricing };
    const url = URL.createObjectURL(new Blob([JSON.stringify(config, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = "plumo-agent-draft.json"; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000); setDownloaded(true);
  }

  function prepareMail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = [
      `${c.contactName}: ${form.get("name")}`, `${c.company}: ${form.get("company")}`, `${c.email}: ${form.get("email")}`,
      String(form.get("message") ?? ""), "", `${c.company}: ${draft.company}`, `${c.description}: ${draft.description}`,
      `${c.agentName}: ${draft.name}`, `${c.channel}: ${c.channels[channel]}`, `${c.knowledge}: ${sources.length}`,
      pricing ? pricingRequestLabel(locale, pricing) : "",
    ].filter(Boolean).join("\n");
    window.location.href = `mailto:contact@plumo.app?subject=${encodeURIComponent(locale === "ru" ? "Plumo — после самостоятельного демо" : "Plumo — self-guided demo follow-up")}&body=${encodeURIComponent(body)}`;
    setMailReady(true);
  }

  return <div className="min-h-svh bg-plumo-line/20 text-plumo-ink">
    <header className="mx-auto flex max-w-[1280px] flex-wrap items-center justify-between gap-3 px-5 py-5 md:px-10">
      <Link href="/" className="text-[13px] text-plumo-muted hover:text-plumo-ink">← {c.home}</Link>
      <Link href="/" aria-label={t.home} className="brand"><span className="brand-crop"><Image src="/images/plumo-logo.png" alt="" width={172} height={172} priority className="brand-image mix-blend-multiply" /></span></Link>
      <LanguageSwitch />
    </header>
    <main className="mx-auto max-w-[1120px] px-4 pb-10 pt-5 md:px-8 md:pt-8">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 text-[12px] text-plumo-muted"><span>{c.step} {step + 1} {c.of} 6 · {c.steps[step]}</span><span className="rounded-full border border-solid border-plumo-line bg-white px-3 py-1.5">{c.demoMode}</span></div>
      <motion.div key={step} initial={reduced ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }} className={`overflow-hidden rounded-[24px] border border-solid border-plumo-line bg-white ${step < 5 ? "grid lg:min-h-[600px] lg:grid-cols-2" : ""}`}>
        {step < 5 ? <>
          <form onSubmit={next} className="flex flex-col p-6 md:p-10">
            <h1 ref={heading} tabIndex={-1} className="m-0 text-[28px] font-medium leading-tight tracking-tight outline-none md:text-[32px]">{c.titles[step]}</h1>
            <p className="mb-8 mt-3 text-[15px] leading-relaxed text-plumo-muted">{c.intros[step]}</p>
            <div className="flex flex-col gap-5">
              {step === 0 && <>
                <Field title={c.purpose}><select value={draft.purpose} onChange={e => update("purpose", e.target.value as AgentDraft["purpose"])} className={input}><option value="sales">{c.sales}</option><option value="support">{c.support}</option></select></Field>
                <div className="flex flex-wrap gap-2" role="group" aria-label={c.alternatives}>{(["website", "instagram", "text", "file", "faq"] as const).map(tab => <button key={tab} type="button" disabled={reading} aria-pressed={kind === tab} onClick={() => { setKind(tab); setValue(""); setQuestion(""); setError(""); }} className={`cursor-pointer rounded-lg border border-solid px-3 py-2 font-[inherit] text-[12px] ${kind === tab ? "border-plumo-ink bg-plumo-ink text-white" : "border-plumo-line bg-white text-plumo-muted"}`}>{c[tab]}</button>)}</div>
                {(kind === "website" || kind === "instagram") && <><Field title={c.sourceLabel}><input value={value} onChange={e => setValue(e.target.value)} placeholder={kind === "instagram" ? "instagram.com/yourcompany" : c.sourcePlaceholder} inputMode="url" maxLength={2000} className={input} /></Field><p className="m-0 text-[12px] leading-relaxed text-plumo-muted">{c.sourceNote}</p></>}
                {kind === "text" && <Field title={c.material}><textarea value={value} onChange={e => setValue(e.target.value)} rows={5} maxLength={50000} placeholder={c.materialPlaceholder} className={input} /></Field>}
                {kind === "faq" && <><Field title={c.question}><input value={question} onChange={e => setQuestion(e.target.value)} maxLength={300} className={input} /></Field><Field title={c.answer}><textarea value={value} onChange={e => setValue(e.target.value)} rows={4} maxLength={5000} className={input} /></Field></>}
                {kind === "file" ? <Field title={c.fileHint}><input type="file" accept=".txt,.md,text/plain,text/markdown" disabled={reading} onChange={e => { void readFile(e.target.files?.[0]); e.target.value = ""; }} className={`${input} file:mr-3 file:rounded-lg file:border-0 file:bg-plumo-soft file:px-3 file:py-2 file:text-plumo-blue`} /></Field> : <button type="button" onClick={addSource} className={secondary}>{c.add} <span aria-hidden="true">+</span></button>}
                {reading && <p role="status" className="m-0 text-[13px] text-plumo-muted">{c.loading}</p>}
                {sources.length > 0 && <ul className="m-0 flex list-none flex-col gap-2 p-0">{sources.map(source => <li key={source.id} className="flex items-center justify-between gap-3 rounded-xl bg-plumo-line/25 px-3 py-2"><span className="min-w-0 truncate text-[12px]" title={source.title}>{source.title}</span><button type="button" aria-label={`${c.remove}: ${source.title}`} onClick={() => { setSources(previous => previous.filter(s => s.id !== source.id)); setDownloaded(false); }} className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-full border-0 bg-transparent text-plumo-muted">×</button></li>)}</ul>}
              </>}
              {step === 1 && <>
                <Field title={c.company}><input required value={draft.company} onChange={e => update("company", e.target.value)} maxLength={100} placeholder={c.companyPlaceholder} className={input} /></Field>
                <Field title={c.description}><textarea required value={draft.description} onChange={e => update("description", e.target.value)} maxLength={1500} rows={4} placeholder={c.descriptionPlaceholder} className={input} /></Field>
                <Field title={c.audience}><input value={draft.audience} onChange={e => update("audience", e.target.value)} maxLength={300} placeholder={c.audiencePlaceholder} className={input} /></Field>
              </>}
              {step === 2 && <>
                <div className="flex items-center gap-4"><Mark draft={draft} size={64} /><div className="min-w-0"><p className="m-0 text-[14px] font-medium">{c.logo}</p><p className="mb-0 mt-2 text-[12px] text-plumo-muted">{c.logoHint}</p></div></div>
                <Field title={c.uploadLogo}><input type="file" accept="image/png,image/jpeg,image/webp" disabled={reading} onChange={e => { void readLogo(e.target.files?.[0]); e.target.value = ""; }} className={`${input} file:mr-2 file:border-0 file:bg-plumo-soft file:p-2 file:text-plumo-blue`} /></Field>
                {draft.logo && <button type="button" onClick={() => { update("logo", ""); update("logoName", ""); }} className={`${secondary} self-start`}>{c.removeLogo}</button>}
                <fieldset className="m-0 border-0 p-0"><legend className="mb-3 text-[13px]">{c.color}</legend><div className="flex flex-wrap gap-3">{["#2b55ff", "#111113", "#16806a", "#8056d9", "#ac4b32"].map(color => <button key={color} type="button" aria-label={color} aria-pressed={draft.color === color} onClick={() => update("color", color)} className="flex size-11 cursor-pointer items-center justify-center rounded-full border-0 text-[20px] text-white outline-offset-4 aria-pressed:outline aria-pressed:outline-2 aria-pressed:outline-plumo-ink" style={{ backgroundColor: color }}>{draft.color === color ? "✓" : ""}</button>)}</div></fieldset>
              </>}
              {step === 3 && <>
                <Field title={c.agentName}><input required value={draft.name} onChange={e => update("name", e.target.value)} maxLength={60} className={input} /></Field>
                <Field title={c.tone}><select value={draft.tone} onChange={e => update("tone", e.target.value as AgentDraft["tone"])} className={input}><option value="friendly">{c.friendly}</option><option value="formal">{c.formal}</option></select></Field>
                <Field title={c.language}><select value={draft.language} onChange={e => update("language", e.target.value as AgentDraft["language"])} className={input}><option value="ru">{c.ru}</option><option value="en">{c.en}</option></select></Field><p className="m-0 text-[12px] leading-relaxed text-plumo-muted">{c.kyNote}</p>
              </>}
              {step === 4 && <>
                <Field title={c.greeting}><textarea required value={draft.greeting} onChange={e => update("greeting", e.target.value)} rows={3} maxLength={1000} className={input} /></Field>
                <Field title={c.goal}><textarea required value={draft.goal} onChange={e => update("goal", e.target.value)} rows={3} maxLength={1500} className={input} /></Field>
                <Field title={c.fallback}><textarea required value={draft.fallback} onChange={e => update("fallback", e.target.value)} rows={3} maxLength={1000} className={input} /></Field>
                <p className="m-0 text-[12px] leading-relaxed text-plumo-muted">{c.scriptNote}</p>
              </>}
            </div>
            <p role="alert" className="mb-0 mt-4 text-[13px] leading-relaxed text-plumo-ink empty:hidden">{error}</p>
            <div className="mt-auto flex gap-3 pt-7">{step > 0 && <button type="button" disabled={reading} onClick={() => { setError(""); setStep(step - 1); }} className={secondary}>← {c.back}</button>}<button type="submit" disabled={reading} className={`${primary} flex-1`}>{step === 4 ? c.test : c.next}<span aria-hidden="true">→</span></button></div>
            {step === 0 && <><div className="my-5 h-px bg-plumo-line" /><button type="button" disabled={reading} onClick={useExample} className={secondary}>{c.sample}</button><p className="mb-0 mt-3 text-center text-[11px] text-plumo-muted">{c.sampleNote}</p></>}
          </form>
          <aside aria-label={c.preview} className="relative flex min-h-[360px] items-center justify-center overflow-hidden border-0 border-t border-solid border-plumo-line bg-plumo-line/15 p-6 md:p-10 lg:border-l lg:border-t-0">
            <div aria-hidden="true" className="pointer-events-none absolute inset-0 opacity-40" style={{ backgroundImage: "radial-gradient(var(--muted) 1px, transparent 1px)", backgroundSize: "24px 24px" }} />
            <div className="relative w-full max-w-[380px] overflow-hidden rounded-[22px] border border-solid border-plumo-line bg-white shadow-[0_24px_55px_#11111314]">
              <div className="flex items-center gap-1.5 border-0 border-b border-solid border-plumo-line px-5 py-4"><span className="size-2 rounded-full bg-plumo-line" /><span className="size-2 rounded-full bg-plumo-line" /><span className="size-2 rounded-full bg-plumo-line" /><span className="ml-auto min-w-0 truncate text-[10px] text-plumo-muted">{c.preview}</span></div>
              {step === 0 ? <div className="px-6 py-9 text-center"><div className="mx-auto flex size-16 items-center justify-center rounded-2xl border border-solid border-plumo-line bg-white text-[28px] text-plumo-muted">↗</div><div className="mx-auto h-12 w-px bg-plumo-line" /><Mark draft={draft} size={64} /><p className="mb-0 mt-6 text-[17px] font-medium">{c.facts}</p><p className="mb-0 mt-3 text-[13px] leading-relaxed text-plumo-muted">{c.factsText}</p><span className="mt-5 inline-flex rounded-full bg-plumo-soft px-3 py-1.5 text-[11px] text-plumo-blue">{sources.length} / 10 · {c.knowledge}</span></div> : <div className="p-6">
                <p className="mb-5 mt-0 text-[10px] tracking-[0.12em] text-plumo-muted">{c.draftLabel}</p>
                <div className="flex items-center gap-3"><Mark draft={draft} /><div className="min-w-0"><p className="m-0 break-words text-[17px] font-semibold">{draft.company || c.emptyPreview}</p><p className="mb-0 mt-1 text-[11px] text-plumo-muted">{draft.name} · {c.notConnected}</p></div></div>
                <p className="mb-0 mt-6 rounded-2xl rounded-tl-sm bg-plumo-line/30 p-4 text-[14px] leading-relaxed">{greeting}</p>
                {step === 1 && <p className="mb-0 mt-5 break-words text-[13px] leading-relaxed text-plumo-muted">{draft.description}</p>}
                {step >= 3 && <ul className="mb-0 mt-6 list-none space-y-3 p-0">{c.rules.map(rule => <li key={rule} className="flex gap-2 text-[12px] leading-relaxed"><span className="text-plumo-blue">✓</span>{rule}</li>)}</ul>}
              </div>}
            </div>
          </aside>
        </> : <div className="p-5 md:p-8">
          <div className="mb-7 flex flex-wrap items-start justify-between gap-4"><div><h1 ref={heading} tabIndex={-1} className="m-0 text-[28px] font-medium tracking-tight outline-none">{c.titles[5]}</h1><p className="mb-0 mt-3 max-w-[550px] text-[14px] leading-relaxed text-plumo-muted">{c.intros[5]}</p></div><button type="button" onClick={() => setStep(0)} className={secondary}>{c.edit}</button></div>
          <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
            <div className="min-w-0 overflow-hidden rounded-[20px] border border-solid border-plumo-line">
              <div className="flex items-center gap-3 border-0 border-b border-solid border-plumo-line p-4"><Mark draft={draft} size={40} /><div className="min-w-0 flex-1"><p className="m-0 truncate text-[15px] font-semibold">{draft.name} · {draft.company}</p><p className="mb-0 mt-1 text-[11px] text-plumo-muted">{c.demoMode}</p></div><button type="button" onClick={() => { setMessages([]); setHandedOff(false); setChatInput(""); }} className="cursor-pointer border-0 bg-transparent p-2 font-[inherit] text-[11px] text-plumo-muted underline">{c.restart}</button></div>
              <div ref={transcript} role="log" aria-label={c.test} aria-live="polite" className="flex h-[340px] flex-col gap-4 overflow-y-auto bg-plumo-line/10 p-4">
                <p className="m-0 max-w-[90%] self-start rounded-2xl rounded-tl-sm border border-solid border-plumo-line bg-white px-4 py-3 text-[14px] leading-relaxed">{greeting}</p>
                {messages.map((message, index) => <div key={index} className={`max-w-[90%] break-words rounded-2xl px-4 py-3 text-[14px] leading-relaxed ${message.role === "user" ? "self-end rounded-tr-sm bg-plumo-ink text-white" : "self-start rounded-tl-sm border border-solid border-plumo-line bg-white"}`}><p className="m-0 whitespace-pre-wrap">{message.text}</p>{message.source && <p className="mb-0 mt-2 text-[10px] text-plumo-muted">{c.source}: {message.source}</p>}</div>)}
              </div>
              <div className="border-0 border-t border-solid border-plumo-line p-4"><p className="mb-3 mt-0 text-[11px] leading-relaxed text-plumo-muted">{c.chatHint}</p><div className="mb-4 flex flex-wrap gap-2">{faqs.map(source => <button key={source.id} type="button" disabled={handedOff} onClick={() => send(source.question!)} className={`${secondary} !min-h-8 !px-3 !py-1.5 !text-[11px] disabled:opacity-40`}>{source.question}</button>)}<button type="button" disabled={handedOff} onClick={() => send(c.handoff)} className={`${secondary} !min-h-8 !px-3 !py-1.5 !text-[11px]`}>{c.handoff}</button></div>{!faqs.length && <p className="text-[12px] text-plumo-muted">{c.noFaq}</p>}
                {handedOff ? <p role="status" className="m-0 rounded-xl bg-plumo-soft p-3 text-[13px] leading-relaxed text-plumo-ink">{c.paused}</p> : <form onSubmit={e => { e.preventDefault(); send(chatInput); }} className="flex gap-2"><input aria-label={c.placeholder} value={chatInput} onChange={e => setChatInput(e.target.value)} maxLength={1000} placeholder={c.placeholder} className={input} /><button type="submit" disabled={!chatInput.trim()} className={primary} aria-label={c.send}>↑</button></form>}
              </div>
            </div>
            <aside className="flex min-w-0 flex-col gap-5 rounded-[20px] bg-plumo-line/20 p-5">
              <div><span className="text-[11px] text-plumo-muted">{c.ready}</span><h2 className="mb-0 mt-3 break-words text-[22px] font-medium">{draft.company}</h2><p className="mb-0 mt-3 text-[13px] leading-relaxed text-plumo-muted">{draft.purpose === "sales" ? c.sales : c.support} · {c.knowledge}: {sources.length}</p></div>
              <Field title={c.channel}><select value={channel} onChange={e => { setChannel(Number(e.target.value)); setDownloaded(false); }} className={input}>{c.channels.map((name, index) => <option key={name} value={index}>{name}</option>)}</select></Field>
              <p className="m-0 text-[12px] leading-relaxed text-plumo-muted">{c.launchHint}</p>
              <button type="button" onClick={() => { setMailReady(false); setContact(true); }} aria-haspopup="dialog" className={primary}>{c.discuss} →</button>
              <button type="button" onClick={download} className={secondary}>{downloaded ? c.downloaded : c.download}</button>
              <p className="m-0 text-[11px] leading-relaxed text-plumo-muted">{c.localNote}</p>
            </aside>
          </div>
        </div>}
      </motion.div>
      <nav aria-label={c.progress} className="mx-auto mt-6 flex max-w-[600px] justify-center gap-2">{c.steps.map((name, index) => <div key={name} aria-current={step === index ? "step" : undefined} className="flex min-w-0 flex-1 flex-col items-center gap-2"><span className={`h-1.5 w-full rounded-full ${index <= step ? "bg-plumo-ink" : "bg-plumo-line"}`} /><span className={`hidden text-[11px] sm:block ${index === step ? "text-plumo-ink" : "text-plumo-muted"}`}>{name}</span></div>)}</nav>
      {step < 5 && <p className="mb-0 mt-5 text-center text-[11px] leading-relaxed text-plumo-muted">{c.localNote}</p>}
    </main>
    {contact && <DemoChoice step="expert" onClose={() => setContact(false)} onBack={() => setContact(false)} onSelect={() => {}} backLabel={locale === "ru" ? "← К тестовому чату" : "← Back to the test"}
      expertForm={<DemoContactForm onSubmit={prepareMail} selection={pricing} mailReady={mailReady} defaults={{ company: draft.company, message: `${c.channel} ${c.channels[channel]}` }} formCopy={{ name: c.contactName, business: c.company, email: c.email, message: c.message, send: c.prepare, mailNote: c.mailNote, mailReady: c.mailReady }} />} />}
  </div>;
}
