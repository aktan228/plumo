"use client";

import type { FormEvent } from "react";
import { useLanguage } from "@/lib/i18n";
import { pricingRequestLabel, type PricingRequest } from "./pricing";

type FormCopy = { name: string; business: string; email: string; message: string; send: string; mailNote: string; mailReady: string };
const fieldClass = "w-full rounded-xl border border-solid border-plumo-line bg-white px-3.5 py-3 font-[inherit] text-[16px] text-plumo-ink focus:border-plumo-blue focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue";

export function DemoContactForm({ onSubmit, selection, mailReady, formCopy, defaults }: {
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  selection: PricingRequest | null;
  mailReady: boolean;
  formCopy: FormCopy;
  defaults?: { company: string; message: string };
}) {
  const { locale } = useLanguage();
  return <form onSubmit={onSubmit} className="flex flex-col gap-4">
    {selection && <p className="m-0 rounded-xl bg-plumo-soft px-4 py-3 text-[12px] leading-relaxed text-plumo-ink">{locale === "ru" ? "Ваш выбор" : "Your selection"}: {pricingRequestLabel(locale, selection)}</p>}
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <label className="flex flex-col gap-2 text-[13px]">{formCopy.name}<input name="name" autoComplete="name" required maxLength={100} className={fieldClass} /></label>
      <label className="flex flex-col gap-2 text-[13px]">{formCopy.business}<input name="company" defaultValue={defaults?.company} autoComplete="organization" required maxLength={150} className={fieldClass} /></label>
    </div>
    <label className="flex flex-col gap-2 text-[13px]">{formCopy.email}<input type="email" name="email" autoComplete="email" required maxLength={254} className={fieldClass} /></label>
    <label className="flex flex-col gap-2 text-[13px]">{formCopy.message}<textarea name="message" defaultValue={defaults?.message} rows={3} required maxLength={1500} className={`${fieldClass} resize-y`} /></label>
    <button type="submit" className="min-h-[48px] cursor-pointer rounded-xl border-0 bg-plumo-ink px-5 py-3 font-[inherit] text-[16px] font-medium text-white transition-opacity hover:opacity-85">{formCopy.send}</button>
    <small className="text-[12px] leading-relaxed text-plumo-muted">{formCopy.mailNote}</small>
    {mailReady && <p role="status" className="m-0 text-[12px] leading-relaxed text-plumo-muted">{formCopy.mailReady}</p>}
  </form>;
}
