"use client";

import { useRef, useState, type FormEvent } from "react";
import { useLanguage } from "@/lib/i18n";
import { leadKey, leadPayload, type LeadSource } from "@/lib/leads";
import { pricingRequestLabel, type PricingRequest } from "./pricing";

type FormCopy = { name: string; business: string; email: string; message: string };
const fieldClass = "w-full rounded-xl border border-solid border-plumo-line bg-white px-3.5 py-3 font-[inherit] text-[16px] text-plumo-ink focus:border-plumo-blue focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue";
const copy = {
  ru: { send: "Отправить заявку", sending: "Отправляем…", note: "Заявка сохранится у нас, команда Plumo ответит на указанную почту.", done: (n: number) => `Заявка №${n} принята. Мы напишем вам на почту.`, failed: "Не удалось отправить заявку. Повторите или напишите на contact@plumo.app.", limited: "Слишком много заявок с этого адреса. Повторите позже или напишите на contact@plumo.app.", invalid: "Проверьте имя, почту и текст заявки." },
  en: { send: "Send request", sending: "Sending…", note: "We store your request; the Plumo team will reply by email.", done: (n: number) => `Request #${n} received. We will email you.`, failed: "Could not send the request. Retry or write to contact@plumo.app.", limited: "Too many requests from this address. Retry later or write to contact@plumo.app.", invalid: "Check the name, email and message." },
};

export function DemoContactForm({ source, selection, formCopy, defaults, context = "" }: {
  source: LeadSource;
  selection: PricingRequest | null;
  formCopy: FormCopy;
  defaults?: { company: string; message: string };
  context?: string;
}) {
  const { locale } = useLanguage();
  const c = copy[locale];
  const key = useRef<string | null>(null);
  const [state, setState] = useState<{ kind: "idle" | "sending" | "done" | "error"; text?: string }>({ kind: "idle" });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (state.kind === "sending") return;
    key.current ??= leadKey();
    const plan = selection ? pricingRequestLabel(locale, selection) : "";
    const payload = leadPayload(new FormData(event.currentTarget), source, locale, key.current, plan, context);
    setState({ kind: "sending" });
    try {
      const response = await fetch("/api/leads", { method: "POST", headers: { "content-type": "application/json", "x-plumo-request": "1" }, body: JSON.stringify(payload) });
      const data = await response.json().catch(() => ({}));
      if (response.ok && typeof data.number === "number") { setState({ kind: "done", text: c.done(data.number) }); return; }
      setState({ kind: "error", text: response.status === 429 ? c.limited : response.status === 422 ? c.invalid : c.failed });
    } catch {
      setState({ kind: "error", text: c.failed });
    }
  }

  if (state.kind === "done") return <p role="status" className="m-0 rounded-xl bg-emerald-50 px-4 py-3 text-[14px] leading-relaxed text-emerald-800">{state.text}</p>;
  return <form onSubmit={submit} onChange={() => { if (state.kind === "error") return; key.current = null; }} className="flex flex-col gap-4">
    {selection && <p className="m-0 rounded-xl bg-plumo-soft px-4 py-3 text-[12px] leading-relaxed text-plumo-ink">{locale === "ru" ? "Ваш выбор" : "Your selection"}: {pricingRequestLabel(locale, selection)}</p>}
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <label className="flex flex-col gap-2 text-[13px]">{formCopy.name}<input name="name" autoComplete="name" required maxLength={100} className={fieldClass} /></label>
      <label className="flex flex-col gap-2 text-[13px]">{formCopy.business}<input name="company" defaultValue={defaults?.company} autoComplete="organization" required maxLength={150} className={fieldClass} /></label>
    </div>
    <label className="flex flex-col gap-2 text-[13px]">{formCopy.email}<input type="email" name="email" autoComplete="email" required maxLength={254} className={fieldClass} /></label>
    <label className="flex flex-col gap-2 text-[13px]">{formCopy.message}<textarea name="message" defaultValue={defaults?.message} rows={3} required maxLength={1500} className={`${fieldClass} resize-y`} /></label>
    <button type="submit" disabled={state.kind === "sending"} className="min-h-[48px] cursor-pointer rounded-xl border-0 bg-plumo-ink px-5 py-3 font-[inherit] text-[16px] font-medium text-white transition-opacity hover:opacity-85 disabled:cursor-wait disabled:opacity-60">{state.kind === "sending" ? c.sending : c.send}</button>
    <small className="text-[12px] leading-relaxed text-plumo-muted">{c.note}</small>
    {state.kind === "error" && <p role="alert" className="m-0 text-[13px] leading-relaxed text-red-700">{state.text}</p>}
  </form>;
}
