"use client";

import { motion, useReducedMotion } from "motion/react";
import { useId, useRef, useState, type KeyboardEvent } from "react";
import { useLanguage } from "@/lib/i18n";

const content = {
  ru: {
    title: "Есть вопросы.", accent: "Есть ответы.",
    description: "Главное о Plumo, подключении и работе вашей команды.",
    contact: "Осталось что-то ещё?", contactDescription: "Напишите нам — разберём вашу задачу вместе.",
  },
  en: {
    title: "Have questions?", accent: "We have answers.",
    description: "What to know about Plumo, setup and working with your team.",
    contact: "Anything else on your mind?", contactDescription: "Get in touch — we’ll work through your needs together.",
  },
};

export function FAQ({ items }: { items: readonly (readonly string[])[] }) {
  const { locale } = useLanguage();
  const c = content[locale];
  const reduced = Boolean(useReducedMotion());
  const [open, setOpen] = useState<number | null>(null);
  const id = useId();
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);

  function navigate(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const targets: Record<string, number> = { ArrowDown: (index + 1) % items.length, ArrowUp: (index - 1 + items.length) % items.length, Home: 0, End: items.length - 1 };
    const target = targets[event.key];
    if (target === undefined) return;
    event.preventDefault();
    buttons.current[target]?.focus();
  }

  return <section id="faq" aria-labelledby="faq-title" className="mx-auto max-w-[1440px] px-6 py-20 text-plumo-ink md:px-8 md:py-28 lg:px-16">
    <div className="grid grid-cols-1 items-start gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:gap-16">
      <div className="lg:sticky lg:top-28">
        <h2 id="faq-title" className="!text-[clamp(38px,4.7vw,64px)] !font-bold !leading-[1.06]">{c.title}<br /><span className="text-plumo-blue">{c.accent}</span></h2>
        <p className="mb-0 mt-6 max-w-[320px] text-[16px] leading-relaxed text-plumo-muted">{c.description}</p>
        <div className="mt-8 hidden max-w-[330px] border-0 border-t border-solid border-plumo-line pt-6 lg:block">
          <p className="m-0 text-[14px] font-medium">{c.contact}</p>
          <p className="mb-3 mt-2 text-[12px] leading-relaxed text-plumo-muted">{c.contactDescription}</p>
          <a href="mailto:contact@plumo.app" className="button-text !text-[13px]"><span>contact@plumo.app</span><span className="button-text-symbol" aria-hidden="true"><span className="symbol-arrow">→</span><span className="symbol-plus">+</span></span></a>
        </div>
      </div>
      <div>
        <div className="flex flex-col gap-3 rounded-[32px] bg-[#f5f6f8] p-3 md:p-4">
          {items.map(([question, answer], index) => {
            const expanded = open === index;
            const questionId = `${id}-question-${index}`;
            const answerId = `${id}-answer-${index}`;
            return <div key={index} className={`overflow-hidden rounded-[22px] border border-solid transition-colors duration-300 motion-reduce:transition-none ${expanded ? "border-[#111113] bg-plumo-ink text-white" : "border-plumo-line bg-white text-plumo-ink"}`}>
              <h3 className="m-0 text-[16px] font-medium">
                <button ref={element => { buttons.current[index] = element; }} id={questionId} type="button" aria-expanded={expanded} aria-controls={answerId} onClick={() => setOpen(current => current === index ? null : index)} onKeyDown={event => navigate(event, index)} className="flex min-h-[80px] w-full cursor-pointer items-center justify-between gap-5 rounded-[22px] border-0 bg-transparent px-5 py-5 text-left font-[inherit] text-[15px] leading-[1.5] text-inherit focus-visible:outline-2 focus-visible:outline-offset-[-4px] focus-visible:outline-plumo-blue md:px-6 md:text-[16px]">
                  <span className="max-w-[450px]">{question}</span>
                  <span aria-hidden="true" className={`relative flex size-8 shrink-0 items-center justify-center rounded-full transition-colors ${expanded ? "bg-plumo-blue text-white" : "bg-plumo-soft text-plumo-blue"}`}><svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M3 8h10" /><motion.path d="M8 3v10" initial={false} animate={{ opacity: expanded ? 0 : 1, rotate: expanded ? 90 : 0 }} transition={{ duration: reduced ? 0 : 0.25 }} style={{ transformOrigin: "8px 8px" }} /></svg></span>
                </button>
              </h3>
              <motion.div id={answerId} role="region" aria-labelledby={questionId} aria-hidden={!expanded} initial={false} animate={{ height: expanded ? "auto" : 0, opacity: expanded ? 1 : 0 }} transition={{ height: { duration: reduced ? 0 : 0.35, ease: [0.22, 1, 0.36, 1] }, opacity: { duration: reduced ? 0 : 0.2 } }} className="overflow-hidden">
                <div className="px-5 pb-6 md:px-6 md:pb-7"><p className="m-0 max-w-[520px] border-0 border-t border-solid border-white/15 pt-5 text-[14px] leading-[1.8] text-white/70">{answer}</p></div>
              </motion.div>
            </div>;
          })}
        </div>
        <div className="mt-6 px-1 lg:hidden"><p className="mb-1 mt-0 text-[13px] text-plumo-muted">{c.contact}</p><a href="mailto:contact@plumo.app" className="button-text !text-[13px]"><span>contact@plumo.app</span><span className="button-text-symbol" aria-hidden="true"><span className="symbol-arrow">→</span><span className="symbol-plus">+</span></span></a></div>
      </div>
    </div>
  </section>;
}
