"use client";

import Link from "next/link";
import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { motion, useReducedMotion } from "motion/react";
import { useLanguage } from "@/lib/i18n";

const copy = {
  ru: {
    title: "С чего начнём?", intro: "Познакомьтесь с Plumo удобным для вас способом.", close: "Закрыть выбор демо",
    formTitle: "Демо с сотрудником", formIntro: "Расскажите о бизнесе и задаче — обсудим подходящий сценарий.", back: "← К выбору способа",
    expert: "Демо с сотрудником", expertText: "Расскажите о своём бизнесе. Вместе разберём задачу и выберем сценарий для первого пилота.",
    expertTags: ["Под ваш бизнес", "Бесплатно"],
    self: "Настроить демо самому", selfText: "Добавьте материалы о бизнесе, настройте агента и проверьте сценарий в тестовом чате.",
    selfTags: ["Без регистрации", "6 шагов"], account: "Уже есть аккаунт?", login: "Войти",
  },
  en: {
    title: "Where shall we start?", intro: "Get to know Plumo in the way that suits you.", close: "Close demo options",
    formTitle: "Demo with our team", formIntro: "Tell us about your business and needs — we’ll discuss a suitable workflow.", back: "← Back to options",
    expert: "Demo with our team", expertText: "Tell us about your business. We’ll discuss your needs and choose a workflow for your first pilot.",
    expertTags: ["Your business", "Free"],
    self: "Set up your own demo", selfText: "Add your business materials, customize your agent and try the workflow in a test chat.",
    selfTags: ["No sign-up", "6 steps"], account: "Already have an account?", login: "Sign in",
  },
};

function ChoiceIcon({ person }: { person?: boolean }) {
  return <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    {person ? <><circle cx="12" cy="8" r="3.5" /><path d="M5 21v-2a7 7 0 0 1 14 0v2M3 10V8a9 9 0 0 1 18 0v2" /></> : <><path d="m4 20 13-13 3 3L7 23ZM14 10l3 3M5 3v4M3 5h4M19 17v4M17 19h4M13 1v4M11 3h4" /></>}
  </svg>;
}

export function DemoChoice({ onClose, onSelect, step, onBack, expertForm, backLabel }: {
  onClose: () => void;
  onSelect: (path: "expert" | "self") => void;
  step: "choice" | "expert";
  onBack: () => void;
  expertForm: ReactNode;
  backLabel?: string;
}) {
  const { locale } = useLanguage();
  const c = copy[locale];
  const dialog = useRef<HTMLDialogElement>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const element = dialog.current;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    element?.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      element?.close();
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, []);

  useEffect(() => {
    dialog.current?.querySelector<HTMLElement>(step === "expert" ? "input" : "button")?.focus({ preventScroll: true });
    if (dialog.current) dialog.current.scrollTop = 0;
  }, [step]);

  return createPortal(<dialog ref={dialog} id="demo-choice" aria-labelledby="demo-choice-title" aria-describedby="demo-choice-description"
    onCancel={event => { event.preventDefault(); onClose(); }}
    onKeyDown={event => {
      if (event.key !== "Tab") return;
      const controls = event.currentTarget.querySelectorAll<HTMLElement>("button:not([disabled]), a[href], input, textarea");
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }}
    onClick={event => { if (event.target === event.currentTarget) onClose(); }}
    className="fixed inset-0 m-auto max-h-[calc(100dvh-32px)] w-[calc(100%-32px)] max-w-[560px] overflow-y-auto overscroll-contain rounded-[28px] border-0 bg-white p-0 text-plumo-ink shadow-2xl backdrop:bg-plumo-ink/45 backdrop:backdrop-blur-sm">
    <motion.div initial={reduced ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className="relative p-6 sm:p-8">
      <button type="button" autoFocus onClick={onClose} aria-label={c.close} className="absolute right-4 top-4 flex size-10 cursor-pointer items-center justify-center rounded-full border border-solid border-plumo-line bg-white text-plumo-muted transition-colors hover:bg-plumo-line/40 hover:text-plumo-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue sm:right-5 sm:top-5"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="m6 6 12 12M18 6 6 18" /></svg></button>
      {step === "expert" && <button type="button" onClick={onBack} className="mb-5 cursor-pointer border-0 bg-transparent p-0 font-[inherit] text-[13px] text-plumo-muted hover:text-plumo-ink">{backLabel || c.back}</button>}
      <h2 id="demo-choice-title" className="m-0 pr-10 text-[28px] font-medium leading-tight tracking-tight sm:text-[32px]">{step === "expert" ? c.formTitle : c.title}</h2>
      <p id="demo-choice-description" className="mb-6 mt-3 max-w-[380px] text-[16px] leading-relaxed text-plumo-muted">{step === "expert" ? c.formIntro : c.intro}</p>
      {step === "expert" ? expertForm : <>
      <div className="flex flex-col gap-3">
        {(["expert", "self"] as const).map(path => {
          const expert = path === "expert";
          return <button key={path} type="button" onClick={() => onSelect(path)} className={`group flex w-full cursor-pointer items-start gap-3 rounded-[20px] border border-solid p-5 text-left font-[inherit] transition-colors focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-plumo-blue sm:gap-4 sm:p-6 ${expert ? "border-plumo-ink bg-plumo-ink text-white hover:bg-plumo-ink/90" : "border-plumo-line bg-white text-plumo-ink hover:bg-plumo-line/20"}`}>
            <span className={`mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl ${expert ? "bg-white/10 text-white" : "bg-plumo-line/50 text-plumo-muted"}`}><ChoiceIcon person={expert} /></span>
            <span className="min-w-0 flex-1"><span className="block text-[18px] font-semibold leading-6">{expert ? c.expert : c.self}</span><span className={`mt-1 block text-[14px] leading-relaxed ${expert ? "text-white/65" : "text-plumo-muted"}`}>{expert ? c.expertText : c.selfText}</span><span className="mt-4 flex flex-wrap gap-2">{(expert ? c.expertTags : c.selfTags).map(tag => <span key={tag} className={`rounded-full px-2.5 py-1 text-[11px] font-medium leading-4 ${expert ? "bg-white/10 text-white/80" : "bg-plumo-line/50 text-plumo-muted"}`}>{tag}</span>)}</span></span>
            <span aria-hidden="true" className={`mt-1 text-[22px] transition-transform group-hover:translate-x-1 motion-reduce:transform-none ${expert ? "text-white/55" : "text-plumo-muted"}`}>→</span>
          </button>;
        })}
      </div>
      <p className="mb-0 mt-6 text-center text-[14px] leading-6 text-plumo-muted">{c.account}{" "}<Link href="/login" onClick={onClose} className="underline underline-offset-4 hover:text-plumo-ink">{c.login}</Link></p>
      </>}
    </motion.div>
  </dialog>, document.body);
}
