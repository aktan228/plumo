"use client";

import Image from "next/image";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { motion, useInView, useReducedMotion } from "motion/react";
import { useLanguage } from "@/lib/i18n";

const copy = {
  ru: {
    title: "Каждый разговор.", accent: "Больше конкретики.",
    intro: "Контакт, потребность и следующий шаг — всё, с чем ваша команда продолжит работу.",
    titles: ["Превращает диалог в заявку", "Собирает контакты", "Уточняет потребность", "Учитывает ваши правки"],
    descriptions: ["Собирает детали в карточку для менеджера. История разговора остаётся рядом — клиенту не нужно объяснять всё заново.", "Спрашивает, как связаться с клиентом, и сохраняет номер вместе с запросом.", "Задаёт вопросы по делу: что нужно клиенту, что важно при выборе и когда удобно продолжить.", "Вы исправляете информацию в базе знаний. Агент использует утверждённые данные в следующих ответах."],
    name: "Айдана", source: "Из WhatsApp", card: "Карточка клиента", contact: "Контакт", phone: "+996 555 00-00-00", need: "Потребность", needValue: "Двухкомнатная квартира для семьи", priority: "Важно", priorityValue: "Школа рядом", next: "Следующий шаг", nextValue: "Уточнить варианты и согласовать просмотр", waiting: "Детали появятся из разговора", history: "Фрагмент переписки", incoming: "Новый запрос",
    askNeed: "Что для вас важнее при выборе квартиры?",
  },
  en: {
    title: "Every conversation.", accent: "More clarity.",
    intro: "A contact, a clear need and a next step — ready for your team to continue.",
    titles: ["Turns conversations into requests", "Collects contact details", "Understands the need", "Uses your corrections"],
    descriptions: ["Organizes the details in a card for your manager. Conversation history stays close, so customers don’t have to repeat themselves.", "Asks how to reach the customer and keeps their number alongside the request.", "Asks relevant questions: what the customer needs, what matters and when to follow up.", "You correct your knowledge base. The agent uses approved information in its next replies."],
    name: "Aidana", source: "From WhatsApp", card: "Customer record", contact: "Contact", phone: "+996 555 00-00-00", need: "Needs", needValue: "A two-bedroom apartment for a family", priority: "What matters", priorityValue: "A school nearby", next: "Next step", nextValue: "Check options and agree on a viewing", waiting: "Details will come from the conversation", history: "Conversation excerpt", incoming: "New inquiry",
    askNeed: "What matters most when choosing an apartment?",
  },
};

function Avatar({ customer = false }: { customer?: boolean }) {
  return <Image src={customer ? "/images/customer-pixel-girl.png" : "/images/plumo-avatar-black.svg"} alt="" width={30} height={30} className="size-[30px] shrink-0 rounded-full" />;
}

function Reveal({ show, reduced, children }: { show: boolean; reduced: boolean; children: ReactNode }) {
  return <motion.div initial={false} animate={{ opacity: show ? 1 : 0, y: show || reduced ? 0 : 10 }} transition={{ duration: reduced ? 0 : 0.45 }} className={!show ? "pointer-events-none" : ""}>{children}</motion.div>;
}

function Bubble({ children, customer = false }: { children: ReactNode; customer?: boolean }) {
  return <div className={`flex items-start gap-2.5 ${customer ? "flex-row-reverse" : ""}`}><Avatar customer={customer} /><p className={`m-0 max-w-[85%] rounded-[16px] px-3.5 py-3 text-[13px] leading-relaxed ${customer ? "rounded-tr-[4px] bg-plumo-blue text-white" : "rounded-tl-[4px] bg-[#f3f4f6] text-plumo-ink"}`}>{children}</p></div>;
}

export function AgentCapabilities() {
  const { locale } = useLanguage();
  return <CapabilitiesExample key={locale} locale={locale} />;
}

function CapabilitiesExample({ locale }: { locale: "ru" | "en" }) {
  const c = copy[locale];
  const section = useRef<HTMLElement>(null);
  const visible = useInView(section, { amount: 0.15 });
  const reduced = Boolean(useReducedMotion());
  const [phase, setPhase] = useState(0);
  const step = reduced ? 4 : phase;
  useEffect(() => {
    if (!visible || reduced) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) setPhase(value => (value + 1) % 8);
    }, 1800);
    return () => window.clearInterval(timer);
  }, [visible, reduced]);

  const footer = (index: number) => <div className="px-1 pb-1 pt-6"><h3 className="m-0 text-[21px] font-semibold tracking-[-0.035em]">{c.titles[index]}</h3><p className="mb-0 mt-3 text-[14px] leading-[1.7] text-plumo-muted">{c.descriptions[index]}</p></div>;

  return <section ref={section} id="product" aria-labelledby="capabilities-title" className="mx-auto max-w-[1440px] px-6 py-20 text-plumo-ink md:px-8 md:py-28 lg:px-16">
    <div className="mx-auto max-w-[800px] text-center"><h2 id="capabilities-title" className="!text-[clamp(38px,5vw,68px)] !font-bold !leading-[1.05]">{c.title}<br /><span className="text-plumo-blue">{c.accent}</span></h2><p className="mx-auto mb-0 mt-6 max-w-[570px] text-[17px] leading-relaxed text-plumo-muted">{c.intro}</p></div>

    <div className="mt-12 grid grid-cols-1 gap-4 md:grid-cols-3 lg:mt-16">
      <article className="rounded-[28px] bg-[#f5f6f8] p-5 md:col-span-3 md:p-7">
        <div className="grid min-h-[280px] grid-cols-1 gap-6 rounded-[20px] bg-white p-5 md:grid-cols-2 md:gap-10 md:p-7">
          <div className="flex flex-col justify-center gap-5"><span className="text-[11px] text-plumo-muted">{c.history}</span><Bubble customer>{c.needValue}</Bubble><Reveal show={step >= 1} reduced={reduced}><Bubble>{c.askNeed}</Bubble></Reveal><Reveal show={step >= 2} reduced={reduced}><Bubble customer>{c.priorityValue}</Bubble></Reveal></div>
          <div className="rounded-[18px] border border-solid border-plumo-line p-5"><div className="flex items-center gap-3"><Avatar customer /><div><p className="m-0 text-[14px] font-semibold">{c.name}</p><p className="mb-0 mt-1 text-[11px] text-plumo-muted">{c.source}</p></div><span className="ml-auto text-[11px] text-plumo-muted">{c.card}</span></div><dl className="mb-0 mt-5">{[[c.need, c.needValue], [c.priority, c.priorityValue], [c.contact, c.phone]].map(([label, value], index) => <div key={label} className="grid grid-cols-[90px_1fr] gap-3 border-0 border-t border-solid border-plumo-line py-3"><dt className="text-[11px] text-plumo-muted">{label}</dt><dd className="m-0 min-h-5 text-[13px]"><Reveal show={step >= index + 1} reduced={reduced}>{value}</Reveal></dd></div>)}</dl><Reveal show={step >= 4} reduced={reduced}><div className="border-0 border-t border-solid border-plumo-line pt-3"><p className="m-0 text-[11px] text-plumo-muted">{c.next}</p><p className="mb-0 mt-2 text-[13px]">{c.nextValue}</p></div></Reveal></div>
        </div>{footer(0)}
      </article>

    </div>
  </section>;
}
