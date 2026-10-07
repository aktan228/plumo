"use client";

import { useLanguage } from "@/lib/i18n";
import { MessengerPreview, ChannelIcon, type Channel } from "./messenger-preview";

const channels: Channel[] = ["whatsapp", "telegram", "instagram"];
const names = ["WhatsApp", "Telegram", "Instagram"];
const content = {
  ru: {
    title: "ИИ-агент работает,", accent: "пока вас нет.",
    description: "Посмотрите, как Plumo может продолжить разговор в привычном клиенту мессенджере.",
    disclosure: "Сценарные макеты интерфейсов. Каналы не подключены.",
    scenarios: [
      { title: "После рабочего дня", time: "22:17", question: "Здравствуйте! Можно узнать подробнее?", answer: "Здравствуйте! Конечно. Что вас интересует и что важно при выборе?", outcome: "Разговор начинается, даже когда рабочий день закончился." },
      { title: "Менеджер занят", time: "14:32", question: "Какой вариант мне подойдёт?", answer: "Давайте разберёмся. Для кого выбираете и на какой бюджет ориентируетесь?", outcome: "Менеджеру проще продолжить разговор, когда потребность уже понятна." },
      { title: "Нужно уточнить у человека", time: "11:08", question: "Можно договориться об особых условиях?", answer: "Уточню у менеджера. Какие условия вы хотели бы обсудить?", outcome: "Вопрос для менеджера — с контекстом, без выдуманных условий." },
    ],
  },
  en: {
    title: "An AI agent works", accent: "while you’re out.",
    description: "See how Plumo could continue the conversation in your customer’s familiar messenger.",
    disclosure: "Scripted interface previews. Channels are not connected.",
    scenarios: [
      { title: "After business hours", time: "22:17", question: "Hi! Could you tell me more?", answer: "Hi! Of course. What are you looking for, and what matters most to you?", outcome: "The conversation starts even after the working day ends." },
      { title: "The manager is busy", time: "14:32", question: "Which option would suit me?", answer: "Let’s figure it out. Who are you choosing for, and what budget do you have in mind?", outcome: "The manager can pick up the conversation with the customer’s needs in context." },
      { title: "A person needs to check", time: "11:08", question: "Could we agree on special terms?", answer: "I’ll check with the manager. Which terms would you like to discuss?", outcome: "A question for the manager, with context and no invented terms." },
    ],
  },
};

export function CustomerSituations() {
  const { locale } = useLanguage();
  const c = content[locale];
  return <section id="customer-situations" aria-labelledby="situations-title" className="mx-auto max-w-[1440px] px-6 py-20 text-plumo-ink md:px-8 md:py-28 lg:px-16">
    <div className="mx-auto max-w-[780px] text-center">
      <h2 id="situations-title" className="!text-[clamp(42px,6vw,82px)] !font-bold !leading-[1.02]">{c.title}<br /><span className="text-plumo-blue">{c.accent}</span></h2>
    </div>
    <div className="mt-12 grid grid-cols-1 gap-12 min-[1100px]:grid-cols-3 min-[1100px]:gap-6 md:mt-16">
      {c.scenarios.map((item, index) => <article key={`${locale}-${channels[index]}`} className="mx-auto w-full min-w-0 max-w-[440px]">
        <div className="mb-5 flex items-center gap-3">
          <ChannelIcon channel={channels[index]} />
          <span className="text-[18px] font-medium tracking-[-0.03em]">{names[index]}</span>
        </div>
        <MessengerPreview channel={channels[index]} scenario={item} locale={locale} delay={index * 8} />
      </article>)}
    </div>
    <p className="mb-0 mt-10 text-center text-[11px] leading-relaxed text-plumo-muted">{c.disclosure}</p>
  </section>;
}
