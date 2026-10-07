"use client";

import Image from "next/image";
import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useLanguage } from "@/lib/i18n";

const content = {
  ru: {
    title: "Ваш бизнес.", accent: "Ваш Plumo.", intro: "От первого знакомства до пилота — четыре шага, которые пройдём вместе.",
    stages: ["Знакомство", "База знаний", "Проверка", "Запуск пилота"],
    titles: ["Начнём с вашей задачи.", "Дадим агенту опору.", "Проверим на ваших вопросах.", "Подключим первый канал."],
    descriptions: ["Разберём, с чем приходят клиенты, какие вопросы повторяются и когда нужен менеджер. Выберем один сценарий для старта.", "Соберём услуги, цены и условия. Вы проверите информацию и определите, что агент может отвечать самостоятельно.", "Пройдём типичные и сложные диалоги. Проверим ответы, сбор контактов и передачу вашей команде.", "Запустим согласованный сценарий. Вместе разберём обращения и уточним ответы по результатам пилота."],
    results: ["Один канал. Одна задача. Понятный результат.", "Утверждённые данные и правила ответов.", "Проверенный сценарий и передача человеку.", "Реальные обращения и обратная связь команды."],
    next: "Следующий шаг", start: "Обсудить пилот", example: "Пример настройки", brief: "Задача бизнеса", fieldLabels: ["Канал", "Запрос клиента", "Результат"], fieldValues: ["WhatsApp", "Подобрать квартиру", "Передать пожелания менеджеру"],
    documents: ["Объекты и цены", "Условия просмотра", "Ответы на вопросы"], approved: "Проверено командой", rule: "Если данных нет — уточнить у менеджера.", question: "Можно посмотреть квартиру в субботу?", answer: "Какое время вам удобно? Менеджер проверит расписание и подтвердит просмотр.", checked: ["Желаемое время собрано", "Просмотр не обещан без подтверждения", "Контекст для менеджера сохранён"],
    launch: "Сценарий первого пилота", flow: ["Входящий запрос", "Ответ Plumo", "Карточка клиента"], review: "Команда разбирает диалоги и уточняет ответы.",
  },
  en: {
    title: "Your business.", accent: "Your Plumo.", intro: "From our first conversation to your pilot — four steps we’ll take together.",
    stages: ["Get acquainted", "Knowledge base", "Test together", "Launch a pilot"],
    titles: ["Start with your task.", "Give your agent a foundation.", "Test with your questions.", "Connect your first channel."],
    descriptions: ["Understand what customers need, which questions repeat and when a manager should step in. Choose one workflow to start.", "Gather services, prices and terms. You review the information and decide what the agent can answer on its own.", "Run through everyday and difficult conversations. Check replies, contact collection and handoff to your team.", "Launch the agreed workflow. Review inquiries together and refine replies based on the pilot."],
    results: ["One channel. One task. A clear outcome.", "Approved information and response rules.", "A tested workflow and human handoff.", "Real inquiries and feedback from your team."],
    next: "Next step", start: "Discuss a pilot", example: "Example setup", brief: "Business brief", fieldLabels: ["Channel", "Customer need", "Outcome"], fieldValues: ["WhatsApp", "Find an apartment", "Share preferences with the manager"],
    documents: ["Listings and prices", "Viewing terms", "Frequently asked questions"], approved: "Reviewed by the team", rule: "If information is missing, check with the manager.", question: "Can I view the apartment on Saturday?", answer: "What time works for you? The manager will check availability and confirm the viewing.", checked: ["Preferred time collected", "No booking promised before confirmation", "Context saved for the manager"],
    launch: "Your first pilot workflow", flow: ["Incoming inquiry", "Plumo reply", "Customer card"], review: "Your team reviews conversations and refines replies.",
  },
};

function StageIcon({ step, className = "" }: { step: number; className?: string }) {
  const paths = [
    <path key="brief" d="M5 4h14v12H9l-4 4V4Zm4 4h6M9 12h4" />,
    <path key="knowledge" d="M5 3h9l5 5v13H5V3Zm9 0v6h5M9 13h6M9 17h4" />,
    <path key="test" d="m7 12 3 3 7-7M12 3l9 4v6c0 4-9 8-9 8s-9-4-9-8V7l9-4Z" />,
    <path key="launch" d="m4 20 4-1-3-3-1 4Zm4-7 7-9h5v5l-9 7-3-3Zm0 0H4l3-5h5m-1 8v4l5-3v-5" />,
  ];
  return <svg aria-hidden="true" className={className} width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">{paths[step]}</svg>;
}

function Tick() {
  return <svg aria-hidden="true" className="shrink-0 text-[#8da5ff]" width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="m4 10 4 4 8-9" /></svg>;
}

export function SetupPipeline() {
  const { locale } = useLanguage();
  const c = content[locale];
  const [active, setActive] = useState(0);
  const reduced = Boolean(useReducedMotion());

  return <section id="how-it-works" aria-labelledby="pipeline-title" className="mx-auto max-w-[1440px] px-6 py-20 text-plumo-ink md:px-8 md:py-28 lg:px-16">
    <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
      <h2 id="pipeline-title" className="!text-[clamp(40px,5vw,68px)] !font-bold !leading-[1.03]">{c.title}<br /><span className="text-plumo-blue">{c.accent}</span></h2>
      <p className="m-0 max-w-[350px] text-[16px] leading-relaxed text-plumo-muted">{c.intro}</p>
    </div>

    <div className="relative mt-12 grid grid-cols-2 gap-x-4 gap-y-6 md:mt-16 md:grid-cols-4 md:gap-0" role="group" aria-label={locale === "ru" ? "Этапы подключения" : "Setup stages"}>
      <div aria-hidden="true" className="absolute left-[12.5%] right-[12.5%] top-7 hidden h-px bg-plumo-line md:block"><motion.div className="h-full origin-left bg-plumo-blue" initial={false} animate={{ scaleX: active / 3 }} transition={{ duration: reduced ? 0 : 0.6 }} /></div>
      {c.stages.map((label, index) => <button key={label} type="button" aria-pressed={active === index} aria-controls="pipeline-detail" onClick={() => setActive(index)} className="group relative flex cursor-pointer flex-col items-center gap-4 rounded-xl border-0 bg-transparent p-0 text-center font-[inherit] focus-visible:outline-2 focus-visible:outline-offset-8 focus-visible:outline-plumo-blue">
        <span className={`relative flex size-14 items-center justify-center rounded-[18px] border border-solid transition-colors duration-300 motion-reduce:transition-none ${active === index ? "border-plumo-blue bg-plumo-blue text-white shadow-[0_8px_24px_#2b55ff28]" : index < active ? "border-plumo-blue bg-plumo-soft text-plumo-blue" : "border-plumo-line bg-white text-plumo-muted group-hover:border-plumo-blue group-hover:text-plumo-blue"}`}><StageIcon step={index} /></span>
        <span className={`text-[13px] font-medium md:text-[15px] ${active === index ? "text-plumo-blue" : "text-plumo-muted"}`}>{label}</span>
      </button>)}
    </div>

    <div id="pipeline-detail" className="mt-10 grid overflow-hidden rounded-[32px] border border-solid border-plumo-line bg-[#f7f8fa] lg:mt-12 lg:grid-cols-[0.9fr_1.1fr]">
      <div className="flex flex-col px-6 py-8 md:p-10 lg:p-12">
        <AnimatePresence mode="wait" initial={false}><motion.div key={`${locale}-${active}`} initial={reduced ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reduced ? 0 : -6 }} transition={{ duration: reduced ? 0 : 0.2 }} className="min-h-[220px] md:min-h-[230px]">
          <h3 className="m-0 max-w-[390px] text-[clamp(28px,3vw,40px)] font-medium leading-[1.12] tracking-[-0.045em]">{c.titles[active]}</h3>
          <p className="mb-0 mt-6 max-w-[400px] text-[15px] leading-[1.8] text-plumo-muted">{c.descriptions[active]}</p>
        </motion.div></AnimatePresence>
        <p className="mb-6 mt-6 border-0 border-t border-solid border-plumo-line pt-5 text-[13px] leading-relaxed">{c.results[active]}</p>
        {active < 3 ? <button type="button" onClick={() => setActive(value => Math.min(3, value + 1))} className="button-text mt-auto cursor-pointer self-start font-[inherit]"><span>{c.next}</span><span className="button-text-symbol" aria-hidden="true"><span className="symbol-arrow">→</span><span className="symbol-plus">+</span></span></button> : <a href="#pilot" className="button-text mt-auto self-start"><span>{c.start}</span><span className="button-text-symbol" aria-hidden="true"><span className="symbol-arrow">→</span><span className="symbol-plus">+</span></span></a>}
      </div>

      <div className="m-3 mt-0 min-w-0 overflow-hidden rounded-[24px] bg-[#101113] text-white md:m-5 lg:ml-0">
        <div className="flex items-center justify-between border-0 border-b border-solid border-white/10 px-5 py-4"><span className="flex items-center gap-2.5 text-[13px]"><Image src="/images/plumo-avatar.svg" alt="" width={22} height={22} />Plumo</span><span className="text-[10px] text-white/45">{c.example}</span></div>
        <div className="flex min-h-[340px] items-center px-5 py-7 md:px-8">
          <AnimatePresence mode="wait" initial={false}><motion.div key={`${locale}-${active}`} initial={reduced ? false : { opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reduced ? 0 : -8 }} transition={{ duration: reduced ? 0 : 0.25 }} className="w-full">
            {active === 0 && <><p className="mb-6 mt-0 text-[18px] font-medium tracking-tight">{c.brief}</p><dl className="m-0">{c.fieldLabels.map((label, index) => <div key={label} className="border-0 border-t border-solid border-white/10 py-4"><dt className="text-[11px] text-white/45">{label}</dt><dd className="mb-0 ml-0 mt-2 text-[15px]">{c.fieldValues[index]}</dd></div>)}</dl></>}
            {active === 1 && <><div className="space-y-3">{c.documents.map(name => <div key={name} className="flex items-center gap-3 rounded-xl border border-solid border-white/10 bg-white/[0.03] px-4 py-3.5"><StageIcon step={1} className="shrink-0 text-white/45" /><div className="min-w-0 flex-1"><p className="m-0 text-[13px]">{name}</p><p className="mb-0 mt-1 text-[10px] text-white/45">{c.approved}</p></div><Tick /></div>)}</div><p className="mb-0 mt-6 text-[12px] leading-relaxed text-white/60">{c.rule}</p></>}
            {active === 2 && <><p className="mb-3 ml-auto mt-0 w-fit max-w-[90%] rounded-[16px] rounded-tr-[4px] bg-plumo-blue px-4 py-3 text-[13px] leading-relaxed">{c.question}</p><p className="mb-6 mt-0 max-w-[95%] rounded-[16px] rounded-tl-[4px] bg-white/[0.07] px-4 py-3 text-[13px] leading-relaxed">{c.answer}</p><ul className="m-0 list-none space-y-3 p-0">{c.checked.map(text => <li key={text} className="flex items-start gap-2 text-[11px] leading-relaxed text-white/60"><Tick />{text}</li>)}</ul></>}
            {active === 3 && <><p className="mb-6 mt-0 text-[17px] font-medium">{c.launch}</p><ol className="m-0 list-none p-0">{c.flow.map((text, index) => <li key={text} className="relative flex min-h-[62px] items-start gap-4">{index < 2 && <span aria-hidden="true" className="absolute left-[17px] top-9 h-[26px] w-px bg-white/15" />}<span className={`flex size-9 shrink-0 items-center justify-center rounded-xl ${index === 1 ? "bg-plumo-blue" : "bg-white/[0.07]"}`}><StageIcon step={index === 0 ? 0 : index === 1 ? 3 : 1} /></span><span className="pt-2 text-[14px]">{text}</span></li>)}</ol><p className="mb-0 mt-4 text-[12px] leading-relaxed text-white/50">{c.review}</p></>}
          </motion.div></AnimatePresence>
        </div>
      </div>
    </div>
  </section>;
}
