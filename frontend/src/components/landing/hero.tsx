"use client";

import { useEffect, useRef, useState } from "react";
import { motion, useInView, useReducedMotion } from "motion/react";
import { useLanguage } from "@/lib/i18n";
import Image from "next/image";
import "./hero.css";

const content = {
  ru: {
    label: "PLUMO / ИИ-АССИСТЕНТ ДЛЯ БИЗНЕСА", title: "Ваш ИИ-\nассистент\nдля бизнеса.",
    description: "Plumo помогает отвечать на входящие обращения, выяснять потребность клиента и передавать вашей команде заявку вместе с историей разговора.",
    demo: "Записаться на демо", try: "Попробовать бесплатно", note: "Сценарное демо без регистрации", agent: "Ваш Plumo", status: "Демонстрационный диалог", customer: "Клиент", typing: "Plumo печатает", input: "Сообщение клиента", disclaimer: "Пример на вымышленных данных",
    messages: ["Здравствуйте! Ищу двухкомнатную квартиру для семьи в южной части города.", "Здравствуйте! В нашем примере есть квартира 64 м² в этом районе. Что для вас важно при выборе?", "Нужна школа рядом. И хотели бы посмотреть в субботу.", "Уточню расстояние до школы у менеджера. Передам ему ваши пожелания и запрос на субботу — он проверит время и подтвердит просмотр."],
  },
  en: {
    label: "PLUMO / AI ASSISTANT FOR BUSINESS", title: "Your AI\nassistant\nfor business.",
    description: "Plumo helps handle incoming inquiries, understand what customers need and hand your team a request with the full conversation context.",
    demo: "Book a demo", try: "Try for free", note: "Scripted demo · No registration", agent: "Your Plumo", status: "Demo conversation", customer: "Customer", typing: "Plumo is typing", input: "Customer message", disclaimer: "Example with fictional data",
    messages: ["Hi! We're looking for a two-bedroom apartment for our family in the south of the city.", "Hi! Our sample listing is a 64 m² apartment in that area. What matters most to you?", "A school nearby. We'd also like to view it on Saturday.", "I'll ask the manager about the school and pass along your preferences and Saturday request. They'll check availability and confirm the viewing."],
  },
};

export function Hero({ onDemo }: { onDemo: () => void }) {
  const { locale } = useLanguage();
  const c = content[locale];
  const reduced = useReducedMotion();
  const root = useRef<HTMLElement>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const inView = useInView(root, { amount: 0.2 });
  const [tick, setTick] = useState(0);
  const [hovered, setHovered] = useState(false);
  const [pinned, setPinned] = useState(false);
  const expanded = hovered || pinned;
  useEffect(() => {
    const log = transcript.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [tick]);
  useEffect(() => {
    setTick(0);
    if (reduced) return;
    const timer = window.setInterval(() => {
      if (inView && !document.hidden) setTick((value) => value + 1);
    }, 40);
    return () => window.clearInterval(timer);
  }, [locale, reduced, inView]);

  // Customer types into the composer, then sends. The agent pauses before replying.
  let elapsed = tick;
  let draft = "";
  let thinking = false;
  const shown: string[] = [];
  for (let i = 0; i < c.messages.length; i++) {
    const text = c.messages[i];
    const pause = i % 2 === 0 ? 20 : 30;
    if (elapsed < pause) { thinking = i % 2 === 1; break; }
    elapsed -= pause;
    if (elapsed < text.length) {
      if (i % 2 === 0) draft = text.slice(0, elapsed);
      else shown.push(text.slice(0, elapsed));
      break;
    }
    elapsed -= text.length;
    shown.push(text);
  }
  const cycleLength = c.messages.reduce((sum, text, i) => sum + text.length + (i % 2 === 0 ? 20 : 30), 0) + 160;
  useEffect(() => { if (tick >= cycleLength) setTick(0); }, [tick, cycleLength]);
  const messages = reduced ? c.messages : shown;
  function viewed(index: number) {
    const sentAt = c.messages.slice(0, index + 1).reduce((sum, text, i) => sum + text.length + (i % 2 === 0 ? 20 : 30), 0);
    return reduced || tick >= sentAt + 15;
  }
  function sendDemoMessage() {
    if (!draft) return;
    const index = messages.length;
    setTick(c.messages.slice(0, index + 1).reduce((sum, text, i) => sum + text.length + (i % 2 === 0 ? 20 : 30), 0));
  }

  return <section ref={root} className={`conversation-hero section-shell${expanded ? " chat-active" : ""}`} aria-label="Plumo">
    <div className="hero-pitch"><h1>{c.title}</h1><p className="hero-pitch-description">{c.description}</p><div className="hero-pitch-actions"><button type="button" className="primary-cta button-pill cursor-pointer font-[inherit] !px-5 !py-4 !text-[13px]" onClick={onDemo} aria-haspopup="dialog">{c.demo}</button><button type="button" className="button-text cursor-pointer font-[inherit] !px-5 !py-4 !text-[13px]" onClick={onDemo} aria-haspopup="dialog"><span>{c.try}</span><span className="button-text-symbol" aria-hidden="true"><span className="symbol-arrow">→</span><span className="symbol-plus">+</span></span></button></div><small>{c.note}</small></div>
    <div className={`hero-preview${expanded ? " preview-expanded" : ""}`} onFocusCapture={() => setHovered(true)} onBlurCapture={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setHovered(false); }} onPointerEnter={(event) => { if (event.pointerType === "mouse") setHovered(true); }} onPointerLeave={() => setHovered(false)} onKeyDown={(event) => { if (event.key === "Escape") { setPinned(false); setHovered(false); } }}>
    <motion.div className={`hero-chat${expanded ? " is-expanded" : ""}`} aria-label={c.status} animate={{ scale: 1 }} transition={{ duration: reduced ? 0 : 1.5, ease: [.22, 1, .36, 1] }}>
      <div className="hero-chat-heading"><div className="hero-traffic-lights" aria-hidden="true"><span className="window-red" /><span className="window-yellow" /><span className="window-green" /></div><div className="hero-window-title"><b>{c.agent}</b><small>{c.status}</small></div><div className="hero-window-controls"><button className="hero-expand" type="button" aria-expanded={expanded} aria-controls="hero-conversation" aria-label={locale === "en" ? (expanded ? "Collapse conversation" : "Expand conversation") : (expanded ? "Свернуть переписку" : "Раскрыть переписку")} onClick={() => { setPinned(!expanded); setHovered(false); }}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.6" /><path d="M10 4v16" stroke="currentColor" strokeWidth="1.6" /></svg></button></div></div>
      <motion.div id="hero-conversation" ref={transcript} className="hero-transcript" aria-live="off" animate={{ height: expanded ? 430 : 290 }} transition={{ duration: reduced ? 0 : 1.3, ease: [.22, 1, .36, 1] }}>
        {messages.map((text, index) => <motion.div key={`${locale}-${index}`} className={`hero-message ${index % 2 ? "from-agent" : "from-customer"}`} initial={reduced ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .35 }}>
          <div>{index % 2 === 0 ? <Image className="hero-customer-avatar" src="/images/customer-pixel-girl.png" alt="" width={40} height={40} /> : <Image className="hero-plumo-avatar" src="/images/plumo-avatar.svg" alt="" width={40} height={40} />}<b>{index % 2 ? "Plumo" : c.customer}</b></div><p>{text}</p>
          {text === c.messages[index] && <footer className={`hero-message-meta${index % 2 === 0 && viewed(index) ? " is-viewed" : ""}`}><time>{`12:${index < 2 ? "04" : "05"}`}</time>{index % 2 === 0 && <><span className="message-checks" aria-label={locale === "en" ? (viewed(index) ? "Viewed" : "Sent") : (viewed(index) ? "Просмотрено" : "Отправлено")}><svg width="20" height="14" viewBox="0 0 20 14" fill="none" aria-hidden="true"><path d="m2 7 3 3 7-7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />{viewed(index) && <path d="m7 7 3 3 7-7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />}</svg></span></>}</footer>}
        </motion.div>)}
        {thinking && !reduced && <div className="hero-thinking"><span /><span /><span /><small>{c.typing}</small></div>}
      </motion.div>
      <div className="hero-composer"><span aria-hidden="true">{draft || c.input}{draft && <i className="typing-caret" />}</span><motion.button type="button" className={draft ? "composer-send active" : "composer-send"} aria-disabled={!draft} onClick={sendDemoMessage} aria-label={locale === "en" ? "Send demo message" : "Отправить сообщение в демо"} whileTap={reduced ? undefined : { scale: .8 }} animate={reduced ? {} : { scale: messages.length % 2 ? [1, .82, 1] : 1 }} transition={{ duration: .35 }}><svg width="19" height="19" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m3 10 18-7-7 18-3-8-8-3Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" /><path d="m11 13 10-10" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg></motion.button></div>
      <small className="hero-chat-disclaimer">{c.disclaimer}</small>
    </motion.div>
    <small className="hero-preview-hint">{locale === "en" ? "Hover or tap the panel icon to expand" : "Наведите курсор или нажмите значок панели, чтобы раскрыть чат"}</small>
    </div>
  </section>;
}
