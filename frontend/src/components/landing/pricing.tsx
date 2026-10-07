"use client";

import { motion, useReducedMotion } from "motion/react";
import { useLanguage } from "@/lib/i18n";

export type PricingChoice = "start" | "business" | "custom" | "demo";

const content = {
  ru: {
    title: "Выберите объём.", subtitle: "Остальное настроим вместе.",
    intro: "Начните с одного канала. Расширяйте подключение, когда вашему бизнесу понадобится больше.",
    currency: "сом", period: "/ месяц", monthly: "Помесячная оплата", soon: "Скоро", pilot: "Для первых пилотов",
    action: "Обсудить подключение", customAction: "Связаться с нами", futureAction: "Обсудить будущий запуск",
    names: { start: "Старт", business: "Бизнес", custom: "Индивидуальный", demo: "Бесплатное демо" },
    descriptions: ["Для небольшого потока обращений", "Для активной работы с клиентами", "Для задач со своими условиями"],
    prices: ["5 900", "12 900", "По запросу"],
    limits: ["1 000 ответов ИИ в месяц", "3 000 ответов ИИ в месяц", "Объём под вашу задачу"],
    features: [
      ["Один согласованный мессенджер", "База знаний вашего бизнеса", "Сбор контактов и потребности", "Карточка клиента и передача менеджеру", "Базовая настройка для первых 2–3 пилотов"],
      ["До трёх мессенджеров", "Всё из тарифа «Старт»", "Подключение поддерживаемой CRM", "Настройка сценариев для вашей команды"],
      ["Согласованный набор каналов", "Интеграции с системами бизнеса", "Индивидуальные сценарии", "План внедрения и поддержки"],
    ],
    businessNote: "Подключение после запуска нескольких каналов и CRM.", customNote: "Стоимость определим после обсуждения задачи.",
    demoTitle: "Сначала познакомимся?", demoText: "Покажем Plumo на примере вашего бизнеса. Бесплатно.", demoAction: "Записаться на демо",
    terms: "Один ответ ИИ — одно исходящее сообщение Plumo. Звонки, платные сообщения провайдеров и сложные интеграции рассчитываются отдельно. Условия пилота согласуем до подключения.",
  },
  en: {
    title: "Choose your volume.", subtitle: "We’ll set up the rest together.",
    intro: "Start with one channel. Expand when your business needs more.",
    currency: "KGS", period: "/ month", monthly: "Monthly billing", soon: "Coming soon", pilot: "For our first pilots",
    action: "Discuss setup", customAction: "Contact us", futureAction: "Discuss a future launch",
    names: { start: "Start", business: "Business", custom: "Custom", demo: "Free demo" },
    descriptions: ["For a smaller flow of inquiries", "For growing customer conversations", "For workflows with specific needs"],
    prices: ["5,900", "12,900", "Let’s talk"],
    limits: ["1,000 AI replies per month", "3,000 AI replies per month", "Volume tailored to your needs"],
    features: [
      ["One agreed messaging channel", "Your business knowledge base", "Contact and needs collection", "Customer card and manager handoff", "Basic setup for the first 2–3 pilots"],
      ["Up to three messaging channels", "Everything in Start", "Supported CRM integration", "Workflows tailored to your team"],
      ["An agreed set of channels", "Integrations with your business systems", "Custom conversation workflows", "An implementation and support plan"],
    ],
    businessNote: "Available after multi-channel and CRM features launch.", customNote: "We’ll quote after discussing your needs.",
    demoTitle: "Let’s meet first.", demoText: "See Plumo with an example from your business. For free.", demoAction: "Book a demo",
    terms: "One AI reply means one outgoing Plumo message. Calls, paid provider messages and custom integrations are priced separately. Pilot terms are agreed before setup.",
  },
};

export function pricingChoiceLabel(locale: "ru" | "en", choice: PricingChoice) {
  return content[locale].names[choice];
}

function Check() {
  return <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 shrink-0"><path d="m5 12 4 4L19 6" /></svg>;
}

export function Pricing({ onChoose }: { onChoose: (choice: PricingChoice) => void }) {
  const { locale } = useLanguage();
  const c = content[locale];
  const reduced = useReducedMotion();
  const plans = ["start", "business", "custom"] as const;

  return <section id="pricing" aria-labelledby="pricing-title" className="mx-auto max-w-[1440px] px-6 py-20 text-plumo-ink md:px-8 md:py-28 lg:px-16">
    <div className="max-w-[900px]">
      <h2 id="pricing-title" className="!text-[clamp(36px,4.7vw,64px)] !font-bold !leading-[1.06]">{c.title}<br /><span className="text-plumo-blue">{c.subtitle}</span></h2>
      <p className="mb-0 mt-6 max-w-[580px] text-[16px] leading-relaxed text-plumo-muted">{c.intro}</p>
    </div>
    <p className="mb-5 mt-10 text-[12px] text-plumo-muted md:mt-14">{c.monthly}</p>
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3 lg:gap-5">
      {plans.map((plan, index) => {
        const featured = plan === "business";
        return <motion.article key={plan} initial={reduced ? false : { opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.15 }} transition={{ duration: reduced ? 0 : 0.5, delay: reduced ? 0 : index * 0.08 }} className={`flex min-w-0 flex-col rounded-[32px] border border-solid p-7 md:p-8 ${featured ? "border-plumo-blue bg-plumo-blue text-white" : "border-plumo-line bg-white text-plumo-ink"}`}>
          <div className="mb-6 min-h-[22px] text-[11px]">{plan === "start" ? <span className="text-plumo-muted">{c.pilot}</span> : featured ? <span className="rounded-full border border-solid border-white/40 px-3 py-1">{c.soon}</span> : null}</div>
          <h3 className="m-0 text-[27px] font-semibold tracking-[-0.04em]">{c.names[plan]}</h3>
          <p className={`mb-0 mt-3 min-h-[44px] text-[14px] leading-relaxed ${featured ? "text-white/85" : "text-plumo-muted"}`}>{c.descriptions[index]}</p>
          <div className="my-8 flex min-h-[80px] flex-col justify-center">
            <div className="flex flex-wrap items-baseline gap-2"><strong className={`${plan === "custom" ? "text-[34px]" : "text-[48px]"} font-medium leading-none tracking-[-0.055em]`}>{c.prices[index]}</strong>{plan !== "custom" && <span className="text-[15px]">{c.currency}</span>}</div>
            {plan !== "custom" && <span className={`mt-3 text-[12px] ${featured ? "text-white/80" : "text-plumo-muted"}`}>{c.period}</span>}
          </div>
          <a href="#pilot" onClick={() => onChoose(plan)} className="login-link button-pill !flex !min-h-[52px] !w-full !justify-center !px-4 !py-3 !text-center !text-[13px] !font-medium">{featured ? c.futureAction : plan === "custom" ? c.customAction : c.action}</a>
          <div className={`mt-8 border-0 border-t border-solid pt-6 ${featured ? "border-white/25" : "border-plumo-line"}`}>
            <p className="mb-5 mt-0 text-[15px] font-semibold">{c.limits[index]}</p>
            <ul className="m-0 flex list-none flex-col gap-4 p-0">{c.features[index].map(feature => <li key={feature} className="flex items-start gap-3 text-[13px] leading-[1.6]"><Check /><span>{feature}</span></li>)}</ul>
          </div>
          {plan !== "start" && <p className={`mb-0 mt-auto pt-8 text-[11px] leading-relaxed ${featured ? "text-white/80" : "text-plumo-muted"}`}>{featured ? c.businessNote : c.customNote}</p>}
        </motion.article>;
      })}
    </div>
    <div className="mt-6 flex flex-col items-start justify-between gap-5 rounded-[24px] bg-plumo-soft px-6 py-7 md:flex-row md:items-center md:px-8">
      <div><h3 className="m-0 text-[20px] font-medium tracking-[-0.035em]">{c.demoTitle}</h3><p className="mb-0 mt-2 text-[14px] leading-relaxed text-plumo-muted">{c.demoText}</p></div>
      <a href="#pilot" onClick={() => onChoose("demo")} className="button-text shrink-0"><span>{c.demoAction}</span><span className="button-text-symbol" aria-hidden="true"><span className="symbol-arrow">→</span><span className="symbol-plus">+</span></span></a>
    </div>
    <p className="mb-0 mt-5 max-w-[940px] text-[11px] leading-[1.7] text-plumo-muted">{c.terms}</p>
  </section>;
}
