// @refresh reset
"use client";

import Image from "next/image";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";
import { useLanguage } from "@/lib/i18n";
import { MessengerIcon } from "./messenger-preview";

const content = {
  ru: {
    title: "От разговора —", accent: "к следующему шагу.",
    description: "Plumo собирает главное. Ваш менеджер продолжает разговор с готовым контекстом.",
    conversation: "Диалог с клиентом", customer: "Айдана", typing: "Печатает…", assistant: "ИИ-ассистент", today: "Сегодня", message: "Сообщение…", send: "Отправить", sent: "Отправлено", read: "Прочитано", context: "Собираем данные", ready: "На рассмотрении",
    card: "Карточка клиента", source: "Из переписки", need: "Потребность", needValue: "Двухкомнатная квартира для семьи",
    important: "Важно клиенту", importantValue: "Школа рядом", time: "Клиенту удобно", timeValue: "Суббота", pending: "Время ещё не согласовано",
    check: "Нужно уточнить", checkValue: "Расстояние до школы и доступное время просмотра",
    next: "Задача менеджеру", nextValue: "Уточнить расстояние до школы и согласовать время просмотра.",
    waiting: "Ждём ответа клиента", open: "Открыть переписку", close: "Скрыть переписку", history: "Полная история разговора",
    note: "Сценарный пример на вымышленных данных. Заявка и просмотр не создаются.",
    messages: [
      "Здравствуйте! Ищу двухкомнатную квартиру для семьи.",
      "Здравствуйте! Что для вас важно при выборе? Когда хотели бы посмотреть квартиру?",
      "Важна школа рядом. Посмотреть хотим в субботу.",
      "Зафиксирую ваши пожелания. Менеджер уточнит расстояние до школы, проверит время и свяжется с вами для подтверждения просмотра.",
    ],
  },
  en: {
    title: "From a conversation", accent: "to the next step.",
    description: "Plumo gathers what matters. Your manager continues the conversation with the context ready.",
    conversation: "Customer conversation", customer: "Aidana", typing: "Typing…", assistant: "AI assistant", today: "Today", message: "Message…", send: "Send", sent: "Sent", read: "Read", context: "Gathering details", ready: "Under review",
    card: "Customer card", source: "From the conversation", need: "Customer needs", needValue: "A two-bedroom apartment for a family",
    important: "What matters", importantValue: "A school nearby", time: "Customer preference", timeValue: "Saturday", pending: "Time not agreed yet",
    check: "Needs checking", checkValue: "Distance to the school and available viewing times",
    next: "Manager’s task", nextValue: "Check the distance to the school and agree on a viewing time.",
    waiting: "Waiting for the customer", open: "Open conversation", close: "Hide conversation", history: "Full conversation history",
    note: "Scripted example with fictional data. No request or viewing is created.",
    messages: [
      "Hi! I’m looking for a two-bedroom apartment for my family.",
      "Hi! What matters most to you? When would you like to view the apartment?",
      "A school nearby is important. We’d like to view it on Saturday.",
      "I’ll note your preferences. The manager will check the distance to the school and available times, then contact you to confirm the viewing.",
    ],
  },
};

function Arrow({ down = false }: { down?: boolean }) {
  return <svg aria-hidden="true" className={down ? "rotate-90 lg:rotate-0" : ""} width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M4 12h16m-6-6 6 6-6 6" /></svg>;
}

function Avatar({ customer = false }: { customer?: boolean }) {
  return <Image src={customer ? "/images/customer-pixel-girl.png" : "/images/plumo-avatar-black.svg"} alt="" width={customer ? 32 : 26} height={customer ? 32 : 26} className="shrink-0 rounded-full" />;
}

function Field({ label, value, ready, waiting, reduced, children }: { label: string; value: string; ready: boolean; waiting: string; reduced: boolean; children?: ReactNode }) {
  return <div className="border-0 border-b border-solid border-plumo-line py-4 last:border-b-0">
    <dt className="text-[11px] text-plumo-muted">{label}</dt>
    <dd className="m-0 mt-2 min-h-[24px] text-[15px] leading-relaxed">
      <AnimatePresence initial={false} mode="wait">
        <motion.div key={ready ? "value" : "waiting"} initial={reduced ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: reduced ? 0 : 0.2 }} className={ready ? "text-plumo-ink" : "text-plumo-muted/60"}>{ready ? value : waiting}{ready && children}</motion.div>
      </AnimatePresence>
    </dd>
  </div>;
}

export function DialogueToLead({ onDiscuss }: { onDiscuss: () => void }) {
  const { locale } = useLanguage();
  // Remount on a language change so the conversation and its extracted fields stay in sync.
  return <DialogueToLeadExample key={locale} locale={locale} onDiscuss={onDiscuss} />;
}

function DialogueToLeadExample({ locale, onDiscuss }: { locale: "ru" | "en"; onDiscuss: () => void }) {
  const c = content[locale];
  const reduced = Boolean(useReducedMotion());
  const section = useRef<HTMLElement>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const visible = useInView(section, { amount: 0.25 });
  const [tick, setTick] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  let offset = 12;
  const timeline = c.messages.map(text => {
    const start = offset;
    const end = start + Math.ceil(text.length / 3);
    offset = end + 14;
    return { start, end };
  });
  const completeAt = timeline[3].end;
  const fadeAt = completeAt + 72;
  const resetAt = fadeAt + 6;
  const position = reduced || historyOpen ? completeAt : tick;
  const fading = !reduced && !historyOpen && tick >= fadeAt;
  const needReady = position >= timeline[0].end;
  const detailsReady = position >= timeline[2].end;
  const complete = position >= completeAt;
  const active = timeline.findIndex(item => position >= item.start && position < item.end);
  const drafting = [0, 2].find(index => position >= timeline[index].start && position < timeline[index].end);
  const waitingForAgent = [1, 3].some(index => position >= timeline[index - 1].end && position < timeline[index].start);
  const draft = drafting === undefined ? "" : c.messages[drafting].slice(0, Math.max(0, position - timeline[drafting].start) * 3);

  useEffect(() => {
    if (!visible || reduced || historyOpen) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) setTick(value => value >= resetAt ? 0 : value + 1);
    }, 70);
    return () => window.clearInterval(timer);
  }, [visible, reduced, historyOpen, resetAt]);

  useEffect(() => {
    if (!transcript.current) return;
    transcript.current.scrollTop = tick === 0 && !historyOpen && !reduced ? 0 : transcript.current.scrollHeight;
  }, [tick, historyOpen, reduced]);

  return <section ref={section} id="demo" tabIndex={-1} aria-labelledby="lead-story-title" className="mx-auto max-w-[1440px] px-6 py-20 text-plumo-ink outline-none md:px-8 md:py-28 lg:px-16">
    <div className="mx-auto max-w-[840px] text-center">
      <h2 id="lead-story-title" className="!text-[clamp(36px,4.8vw,64px)] !font-bold !leading-[1.04]">{c.title}<br /><span className="text-plumo-blue">{c.accent}</span></h2>
      <p className="mx-auto mb-0 mt-6 max-w-[560px] text-[17px] leading-relaxed text-plumo-muted">{c.description}</p>
    </div>

    <div className="mt-12 rounded-[32px] bg-[#f7f8fa] p-4 md:p-8 lg:mt-16 lg:p-10">
      <div className="grid grid-cols-1 items-center gap-5 lg:grid-cols-[1fr_48px_1fr] lg:gap-4">
        <div role="group" aria-label={`WhatsApp: ${c.conversation}`} className="flex h-[500px] min-w-0 touch-pan-y flex-col self-stretch overflow-hidden rounded-[28px] border border-solid border-[#e3e5e9] bg-[#efeae2] shadow-[0_8px_35px_#11111309] lg:h-auto">
          <div className="relative z-10 flex h-[76px] shrink-0 items-center gap-3 border-0 border-b border-solid border-black/5 bg-[#fafbf8] px-4">
            <MessengerIcon name="back" /><span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-white"><Avatar /></span>
            <div className="min-w-0 flex-1"><p className="m-0 truncate text-[15px] font-semibold">Plumo</p><p className="mb-0 mt-1 truncate text-[11px] text-plumo-muted">{waitingForAgent || active % 2 === 1 ? c.typing : c.assistant}</p></div>
            <MessengerIcon name="phone" /><MessengerIcon name="video" />
          </div>
          <div className="relative min-h-0 flex-1 overflow-hidden bg-[#efeae2] lg:min-h-[420px]">
            <div aria-hidden="true" className="pointer-events-none absolute inset-0 opacity-[0.30] mix-blend-multiply" style={{ backgroundImage: "url('/images/messengers/whatsapp-wallpaper.png')", backgroundSize: "360px auto", backgroundRepeat: "repeat" }} />
            <div ref={transcript} className="relative flex h-full touch-pan-y flex-col overflow-hidden px-4 py-5">
            <div className="mb-6 shrink-0 text-center"><span className="rounded-lg bg-white/75 px-3 py-1.5 text-[10px] text-[#667469]">{c.today}</span></div>
            <motion.div animate={{ opacity: fading ? 0 : 1 }} transition={{ duration: reduced ? 0 : 0.3 }} className="flex shrink-0 flex-col gap-4">
              {c.messages.map((text, index) => {
                const customer = index % 2 === 0;
                if (position < (customer ? timeline[index].end : timeline[index].start)) return null;
                const shown = customer ? text : text.slice(0, Math.max(0, position - timeline[index].start) * 3);
                const viewed = customer && position >= timeline[index + 1].start;
                return <motion.div key={index} initial={reduced ? false : { opacity: 0, y: 22, x: customer ? 12 : -8, scale: 0.9 }} animate={{ opacity: 1, y: 0, x: 0, scale: 1 }} transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 230, damping: 24 }} className={`max-w-[87%] rounded-[18px] px-3.5 py-2.5 ${customer ? "ml-auto origin-bottom-right rounded-tr-[5px] bg-[#d9fdd3] text-[#182c20]" : "mr-auto origin-bottom-left rounded-tl-[5px] bg-white text-plumo-ink shadow-[0_1px_2px_#0000000a]"}`}>
                  <p className="m-0 text-[14px] leading-[1.55]">{shown || "…"}</p>
                  <div className="mt-1 flex items-center justify-end gap-1 text-[9px] text-[#657c72]"><time>{index < 2 ? "12:04" : "12:05"}</time>{customer && <svg aria-label={viewed ? c.read : c.sent} width="18" height="12" viewBox="0 0 22 14" fill="none" stroke={viewed ? "#3390ec" : "currentColor"} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="m2 7 4 4L15 2" />{viewed && <path d="m10 9 2 2 9-9" />}</svg>}</div>
                </motion.div>;
              })}
              {waitingForAgent && <div role="status" aria-label={c.typing} className="flex h-10 w-fit items-center gap-1 rounded-[18px] bg-white px-4">{[0, 1, 2].map(dot => <motion.span key={dot} aria-hidden="true" className="size-1.5 rounded-full bg-[#91999f]" animate={reduced ? undefined : { opacity: [0.35, 1, 0.35], y: [0, -2, 0] }} transition={{ duration: 1.2, repeat: Infinity, delay: dot * 0.16 }} />)}</div>}
            </motion.div>
            </div>
          </div>
          <div className="relative z-10 flex min-h-[68px] shrink-0 items-center gap-2 border-0 border-t border-solid border-black/5 bg-[#f5f3ef] px-3 pb-3 pt-2">
            <span className="text-[#697b73]"><MessengerIcon name="plus" /></span>
            <div className="flex h-[42px] min-w-0 flex-1 items-center gap-2 rounded-full border border-solid border-[#e7e3de] bg-white px-3">
              <span className="text-[#87939c]"><MessengerIcon name="smile" /></span>
              <input readOnly tabIndex={-1} value={draft} placeholder={c.message} aria-label={c.message} className="pointer-events-none h-full w-full min-w-0 flex-1 border-0 bg-transparent p-0 font-[inherit] text-[13px] text-plumo-ink outline-none placeholder:text-[#87939c]" />
              <span className="text-[#87939c]"><MessengerIcon name="camera" /></span>
            </div>
            <motion.button type="button" aria-label={c.send} title={c.send} aria-disabled={!draft || fading} onClick={() => { if (draft && !fading && drafting !== undefined) setTick(timeline[drafting].end); }} animate={{ scale: !reduced && drafting !== undefined && position >= timeline[drafting].end - 2 ? 0.88 : 1 }} transition={{ duration: reduced ? 0 : 0.15 }} whileTap={reduced ? undefined : { scale: 0.88 }} className="flex size-[38px] shrink-0 cursor-pointer items-center justify-center rounded-full border-0 bg-[#128c7e] text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue aria-disabled:cursor-default"><MessengerIcon name="send" /></motion.button>
          </div>
        </div>

        <div aria-hidden="true" className="flex justify-center text-plumo-blue"><motion.span animate={reduced ? undefined : { opacity: complete ? 1 : [0.35, 1, 0.35] }} transition={{ duration: 2, repeat: complete ? 0 : Infinity }} className="flex size-12 items-center justify-center rounded-full bg-white"><Arrow down /></motion.span></div>

        <motion.div animate={{ opacity: fading ? 0 : 1 }} transition={{ duration: reduced ? 0 : 0.3 }} className="min-w-0 rounded-[24px] bg-white p-5 shadow-[0_16px_45px_#2b55ff0a] md:p-7">
          <div className="flex items-start justify-between gap-4"><p className="m-0 text-[14px] font-semibold">{c.card}</p><span className="shrink-0 text-right text-[12px] leading-relaxed text-plumo-muted">{complete ? c.ready : c.context}</span></div>
          <div className="mt-5 flex items-center gap-3"><Avatar customer /><div><p className="m-0 text-[20px] font-semibold tracking-[-0.03em]">{c.customer}</p><p className="mb-0 mt-1 text-[11px] text-plumo-muted">{c.source}</p></div></div>
          <dl className="mb-0 mt-5">
            <Field label={c.need} value={c.needValue} ready={needReady} waiting={c.waiting} reduced={reduced} />
            <Field label={c.important} value={c.importantValue} ready={detailsReady} waiting={c.waiting} reduced={reduced} />
            <Field label={c.time} value={c.timeValue} ready={detailsReady} waiting={c.waiting} reduced={reduced}><span className="mt-1 block text-[12px] leading-relaxed text-plumo-muted">{c.pending}</span></Field>
            <Field label={c.check} value={c.checkValue} ready={complete} waiting={c.waiting} reduced={reduced} />
          </dl>
          <div className="mt-4 border-0 border-t border-solid border-plumo-line pt-5"><p className="m-0 text-[12px] font-semibold text-plumo-ink">{c.next}</p><p className="mb-0 mt-2 min-h-[44px] text-[14px] leading-relaxed text-plumo-ink">{complete ? c.nextValue : "—"}</p></div>
          <button type="button" aria-expanded={historyOpen} aria-controls="lead-conversation-history" onClick={() => { if (!historyOpen) setTick(completeAt); setHistoryOpen(value => !value); }} className="button-text mt-3 cursor-pointer font-[inherit] !text-plumo-blue"><span>{historyOpen ? c.close : c.open}</span><span aria-hidden="true" className="button-text-symbol"><span className="symbol-arrow">→</span><span className="symbol-plus">+</span></span></button>
        </motion.div>
      </div>

      <AnimatePresence initial={false}>
        {historyOpen && <motion.div id="lead-conversation-history" role="region" aria-labelledby="lead-history-title" initial={reduced ? false : { height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: reduced ? 0 : 0.35 }} className="overflow-hidden">
          <div className="mt-8 rounded-[24px] bg-white p-5 md:p-7"><h3 id="lead-history-title" className="m-0 text-[18px] font-semibold">{c.history}</h3><ol className="mb-0 mt-6 list-none space-y-6 p-0">{c.messages.map((text, index) => <li key={index}><div className="flex items-center gap-3 text-[12px] font-semibold"><span className={index % 2 ? "text-plumo-blue" : "text-plumo-ink"}>{index % 2 ? "Plumo" : c.customer}</span><time className="text-[10px] font-normal text-plumo-muted">{index < 2 ? "12:04" : "12:05"}</time></div><p className="mb-0 mt-2 max-w-[780px] text-[14px] leading-relaxed">{text}</p></li>)}</ol></div>
        </motion.div>}
      </AnimatePresence>
    </div>
    <p className="mb-0 mt-6 text-center text-[11px] leading-relaxed text-plumo-muted">{c.note}</p>
    <div className="mt-8 flex flex-col items-center gap-4 text-center">
      <p className="m-0 text-[16px] text-plumo-muted">{locale === "ru" ? "Как это может работать в вашем бизнесе?" : "How could this work for your business?"}</p>
      <button type="button" onClick={onDiscuss} className="cursor-pointer rounded-full border-0 bg-plumo-ink px-6 py-4 font-[inherit] text-[14px] font-medium text-white transition-opacity hover:opacity-85">{locale === "ru" ? "Обсудить с сотрудником" : "Discuss with our team"}</button>
    </div>
  </section>;
}
