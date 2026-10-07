"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { CSSProperties, FormEvent } from "react";
import { useLanguage } from "@/lib/i18n";
import { pricingRequestLabel, type PricingRequest } from "./pricing";

type FormCopy = { name: string; business: string; email: string; message: string; send: string; mailNote: string; mailReady: string };
type Props = {
  expanded: boolean;
  onToggle: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  selection: PricingRequest | null;
  mailReady: boolean;
  formCopy: FormCopy;
};

const copy = {
  ru: { title: "Ваш бизнес на связи.", subtitle: "Даже когда вас нет.", action: "Записаться на демо", close: "Скрыть форму", formTitle: "Начнём с вашего бизнеса", chosen: "Ваш выбор", description: "Расскажите о задаче — вместе выберем сценарий первого пилота." },
  en: { title: "Your business stays connected.", subtitle: "Even when you’re away.", action: "Book a demo", close: "Hide form", formTitle: "Let’s start with your business", chosen: "Your selection", description: "Tell us what you need — we’ll choose a workflow for your first pilot together." },
};

const buttonTheme = { "--button-base": "#fff", "--button-ink": "#111113", "--button-wave": "#2b55ff", "--button-hover-ink": "#fff" } as CSSProperties;
const fieldClass = "w-full rounded-[14px] border border-solid border-white/20 bg-white/[0.04] px-4 py-3.5 font-[inherit] text-[15px] text-white outline-none transition-colors focus:border-plumo-blue focus-visible:ring-2 focus-visible:ring-plumo-blue/40";

export function PilotCTA({ expanded, onToggle, onSubmit, selection, mailReady, formCopy }: Props) {
  const { locale } = useLanguage();
  const c = copy[locale];
  const reduced = Boolean(useReducedMotion());

  return <section id="pilot" aria-labelledby="pilot-title" className="bg-[#0a0a0a] px-6 py-20 text-white md:px-8 md:py-24 lg:px-16">
    <div className="mx-auto max-w-[1200px] text-center">
      <h2 id="pilot-title" className="!m-0 !text-[clamp(32px,4.5vw,62px)] !font-medium !leading-[1.15] !tracking-[-0.045em]">{c.title}<br /><span className="text-[#85858e]">{c.subtitle}</span></h2>
      <button type="button" aria-expanded={expanded} aria-controls="pilot-contact-form" onClick={onToggle} style={buttonTheme} className="login-link button-pill mx-auto mt-10 !min-h-[52px] cursor-pointer !border-white !px-7 !py-4 font-[inherit] !text-[14px] !font-medium focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-plumo-blue">{expanded ? c.close : c.action}</button>
    </div>
    <div id="pilot-contact-form"><AnimatePresence initial={false}>
      {expanded && <motion.div key="form" initial={reduced ? false : { height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: reduced ? 0 : 0.4 }} className="mx-auto max-w-[680px] overflow-hidden text-left">
        <div className="mt-12 rounded-[28px] border border-solid border-white/15 bg-[#121214] p-6 md:p-8">
          <h3 className="m-0 text-[23px] font-medium tracking-tight">{c.formTitle}</h3>
          <p className="mb-7 mt-3 text-[13px] leading-relaxed text-white/55">{c.description}</p>
          <form onSubmit={onSubmit} className="flex flex-col gap-5">
            {selection && <p role="status" className="m-0 border-0 border-b border-solid border-white/15 pb-5 text-[12px] leading-relaxed text-white/70">{c.chosen}: {pricingRequestLabel(locale, selection)}</p>}
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <label className="flex flex-col gap-2.5 text-[12px] text-white/70">{formCopy.name}<input name="name" autoComplete="name" required maxLength={100} className={fieldClass} /></label>
              <label className="flex flex-col gap-2.5 text-[12px] text-white/70">{formCopy.business}<input name="company" autoComplete="organization" required maxLength={150} className={fieldClass} /></label>
            </div>
            <label className="flex flex-col gap-2.5 text-[12px] text-white/70">{formCopy.email}<input type="email" name="email" autoComplete="email" required maxLength={254} className={fieldClass} /></label>
            <label className="flex flex-col gap-2.5 text-[12px] text-white/70">{formCopy.message}<textarea name="message" rows={3} required maxLength={1500} className={`${fieldClass} resize-y`} /></label>
            <button type="submit" style={buttonTheme} className="login-link button-pill !min-h-[52px] cursor-pointer !border-white !px-6 !py-4 font-[inherit] !text-[14px] !font-medium focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-plumo-blue">{formCopy.send}</button>
            <small className="text-[11px] leading-relaxed text-white/50">{formCopy.mailNote}</small>
            {mailReady && <p role="status" className="m-0 text-[12px] leading-relaxed text-white/70">{formCopy.mailReady}</p>}
          </form>
        </div>
      </motion.div>}
    </AnimatePresence></div>
  </section>;
}
