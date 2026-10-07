"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";

export type Channel = "whatsapp" | "telegram" | "instagram";
type Scenario = { title: string; time: string; question: string; answer: string; outcome: string };
type IconName = "back" | "phone" | "video" | "more" | "plus" | "smile" | "camera" | "mic" | "send";
const iconPaths: Record<IconName, string> = {
  back: "m14 5-7 7 7 7",
  phone: "M8 3H4a1 1 0 0 0-1 1c0 9.4 7.6 17 17 17a1 1 0 0 0 1-1v-4l-5-2-2 3a15 15 0 0 1-7-7l3-2Z",
  video: "M16 9l5-3v12l-5-3M4 5h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z",
  more: "M12 5h.01M12 12h.01M12 19h.01",
  plus: "M12 5v14M5 12h14",
  smile: "M8 14s1 3 4 3 4-3 4-3M8 9h.01M16 9h.01",
  camera: "M8 5l2-2h4l2 2h4a1 1 0 0 1 1 1v13H3V6a1 1 0 0 1 1-1Z",
  mic: "M8 4a4 4 0 0 1 8 0v8a4 4 0 0 1-8 0ZM5 10v2a7 7 0 0 0 14 0v-2M12 19v4M8 23h8",
  send: "m21 3-7 18-4-7-7-4 18-7ZM10 14 21 3",
};
function Icon({ name }: { name: IconName }) {
  return <svg aria-hidden="true" className="shrink-0" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={name === "more" ? 3 : 1.6} strokeLinecap="round" strokeLinejoin="round"><path d={iconPaths[name]} />{name === "smile" && <circle cx="12" cy="12" r="9" />}{name === "camera" && <circle cx="12" cy="12" r="4" />}</svg>;
}
export function ChannelIcon({ channel }: { channel: Channel }) {
  const bg = channel === "whatsapp" ? "bg-[#25d366]" : channel === "telegram" ? "bg-[#2aabee]" : "bg-linear-to-tr from-[#ffb545] via-[#ed327b] to-[#7445da]";
  return <span className={`flex size-9 shrink-0 items-center justify-center rounded-[11px] text-white ${bg}`}><svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    {channel === "whatsapp" && <path fill="currentColor" stroke="none" d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z" />}
    {channel === "telegram" && <path fill="currentColor" stroke="none" d="m20.8 4.2-3 15c-.2 1-1 .9-1.5.6l-4.5-3.3-2.2 2.1c-.2.2-.4.3-.7.3l.3-4.6 8.5-7.7c.4-.3-.1-.5-.5-.2L6.7 13 2.3 11.6c-1-.3-1-1 .2-1.4L20 3.5c.8-.3 1.1.2.8.7Z" />}
    {channel === "instagram" && <><rect x="3.5" y="3.5" width="17" height="17" rx="5" /><circle cx="12" cy="12" r="4" /><circle cx="17.5" cy="6.5" r=".8" fill="currentColor" stroke="none" /></>}
  </svg></span>;
}
function PlumoAvatar({ large = false }: { large?: boolean }) {
  return <span className={`flex shrink-0 items-center justify-center rounded-full bg-white ${large ? "size-14" : "size-9"}`}><Image src="/images/plumo-avatar-black.svg" alt="" width={large ? 44 : 28} height={large ? 44 : 28} /></span>;
}
const copy = {
  ru: { today: "Сегодня", assistant: "ИИ-ассистент", bot: "бот", message: "Сообщение…", replay: "Повторить", send: "Отправить", typing: "Plumo печатает", sent: "Отправлено", viewed: "Прочитано" },
  en: { today: "Today", assistant: "AI assistant", bot: "bot", message: "Message…", replay: "Replay", send: "Send", typing: "Plumo is typing", sent: "Sent", viewed: "Read" },
};
export function MessengerPreview({ channel, scenario, locale, delay }: { channel: Channel; scenario: Scenario; locale: "ru" | "en"; delay: number }) {
  const c = copy[locale];
  const reduced = useReducedMotion();
  const root = useRef<HTMLDivElement>(null);
  const conversation = useRef<HTMLDivElement>(null);
  const visible = useInView(root, { amount: 0.4 });
  const [tick, setTick] = useState(0);
  const wa = channel === "whatsapp", tg = channel === "telegram", ig = channel === "instagram";
  const sendAt = delay + Math.ceil(scenario.question.length / 2) + 9;
  const answerAt = sendAt + 20;
  const end = answerAt + Math.ceil(scenario.answer.length / 3);
  // Leave the completed reply readable for four seconds before the next cycle.
  const clearAt = end + Math.ceil(4000 / 65);
  const restartAt = clearAt + 6;
  const clearing = !reduced && tick >= clearAt;
  const sent = reduced || tick >= sendAt;
  const answering = reduced || tick >= answerAt;
  const waiting = sent && !answering;
  const draft = sent || clearing ? "" : scenario.question.slice(0, Math.max(0, tick - delay) * 2);
  const answer = reduced ? scenario.answer : scenario.answer.slice(0, Math.max(0, tick - answerAt) * 3);
  useEffect(() => {
    if (!conversation.current) return;
    if (tick === 0) conversation.current.scrollTop = 0;
    else if (sent) conversation.current.scrollTop = conversation.current.scrollHeight;
  }, [tick, sent]);
  useEffect(() => {
    if (!visible || reduced) return;
    const timer = window.setInterval(() => { if (!document.hidden) setTick(value => value >= restartAt ? 0 : value + 1); }, 65);
    return () => window.clearInterval(timer);
  }, [visible, reduced, restartAt]);
  const background = wa ? "bg-[#efeae2]" : tg ? "bg-[#99ba92]" : "bg-white";
  const outgoing = wa ? "rounded-tr-[5px] bg-[#d9fdd3] text-[#182c20]" : tg ? "rounded-br-[5px] bg-[#d8edff] text-[#17364d]" : "bg-plumo-blue text-white";
  const incoming = ig ? "bg-[#f2f2f2]" : "bg-white shadow-[0_1px_2px_#0000000a]";
  return <>
    <div ref={root} role="group" aria-label={`${channel}: ${scenario.title}`} className={`flex h-[500px] touch-pan-y flex-col overflow-hidden rounded-[28px] border border-solid border-[#e3e5e9] shadow-[0_8px_35px_#11111309] ${background}`}>
      <div className={`relative z-10 flex h-[76px] shrink-0 items-center gap-3 border-0 border-b border-solid border-black/5 px-4 ${wa ? "bg-[#fafbf8]" : "bg-white"}`}>
        <span className={tg ? "text-[#3390ec]" : "text-plumo-ink"}><Icon name="back" /></span><PlumoAvatar />
        <div className="min-w-0 flex-1"><p className="m-0 truncate text-[15px] font-semibold">{ig ? "plumo.ai" : "Plumo"}</p><p className="mb-0 mt-1 truncate text-[11px] text-plumo-muted">{waiting ? c.typing : tg ? c.bot : c.assistant}</p></div>
        <span className={tg ? "text-[#3390ec]" : "text-plumo-ink"}><Icon name={tg ? "more" : "phone"} /></span>{!tg && <Icon name="video" />}
      </div>
      <div className="relative min-h-0 flex-1 overflow-hidden" style={tg ? { backgroundImage: "radial-gradient(ellipse at 0% 0%, #bdcd8c, transparent 65%), radial-gradient(ellipse at 100% 0%, #8eba89, transparent 65%), radial-gradient(ellipse at 0% 100%, #83b28f, transparent 65%), linear-gradient(#c5d3b0, #c5d3b0)" } : undefined}>
        {!ig && <div aria-hidden="true" className={`pointer-events-none absolute inset-0 ${wa ? "opacity-[0.13] mix-blend-multiply" : "opacity-[0.10]"}`} style={{ backgroundImage: `url('/images/messengers/${wa ? "whatsapp-wallpaper.png" : "telegram-pattern.svg"}')`, backgroundSize: wa ? "360px auto" : "440px auto" }} />}
        <div ref={conversation} className="relative flex h-full touch-pan-y flex-col overflow-hidden px-4 py-5">
        {ig ? <div className="mb-5 flex shrink-0 flex-col items-center gap-2"><PlumoAvatar large /><span className="text-[14px] font-semibold">Plumo</span><span className="text-[10px] text-plumo-muted">plumo.ai</span></div> : <div className="mb-6 shrink-0 text-center"><span className={`rounded-lg px-3 py-1.5 text-[10px] ${wa ? "bg-white/75 text-[#667469]" : "bg-[#577b50]/40 text-white"}`}>{c.today}</span></div>}
        <motion.div className="flex shrink-0 flex-col gap-4" animate={{ opacity: clearing ? 0 : 1 }} transition={{ duration: reduced ? 0 : 0.25 }}>
          <AnimatePresence initial={!reduced}>
          {sent && <motion.div key="customer" initial={reduced ? false : { opacity: 0, y: 24, x: 12, scale: 0.88 }} animate={{ opacity: 1, y: 0, x: 0, scale: 1 }} transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 230, damping: 24 }} className={`ml-auto max-w-[87%] origin-bottom-right rounded-[18px] px-3.5 py-2.5 ${outgoing}`}>
            <p className="m-0 text-[14px] leading-[1.55]">{scenario.question}</p>
            {!ig && <div className="mt-1 flex items-center justify-end gap-1 text-[9px] text-[#657c72]"><time>{scenario.time}</time><svg aria-label={answering ? c.viewed : c.sent} width="18" height="12" viewBox="0 0 22 14" fill="none" stroke={answering ? "#3390ec" : "currentColor"} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="m2 7 4 4L15 2" />{answering && <path d="m10 9 2 2 9-9" />}</svg></div>}
          </motion.div>}
          </AnimatePresence>
          <div className="flex items-end gap-2">
            {ig && (waiting || answering) && <span className="mb-1"><PlumoAvatar /></span>}
            <AnimatePresence mode="wait" initial={!reduced}>
            {waiting && <motion.div key="typing" role="status" aria-label={c.typing} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.9 }} transition={{ duration: 0.18 }} className={`flex h-10 items-center gap-1 rounded-[18px] px-4 ${incoming}`}>{[0, 1, 2].map(dot => <motion.span key={dot} aria-hidden="true" className="size-1.5 rounded-full bg-[#91999f]" animate={{ opacity: [0.35, 1, 0.35], y: [0, -2, 0] }} transition={{ duration: 1.2, repeat: Infinity, delay: dot * 0.16 }} />)}</motion.div>}
            {answering && <motion.div key="reply" initial={reduced ? false : { opacity: 0, y: 22, x: -8, scale: 0.9 }} animate={{ opacity: 1, y: 0, x: 0, scale: 1 }} transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 230, damping: 24 }} className={`min-w-0 max-w-[87%] origin-bottom-left rounded-[18px] px-3.5 py-2.5 text-plumo-ink ${!ig ? "rounded-tl-[5px]" : ""} ${incoming}`}><p className="m-0 min-h-[22px] text-[14px] leading-[1.55]">{answer || "…"}</p>{!ig && <time className="mt-1 block text-right text-[9px] text-plumo-muted">{scenario.time}</time>}</motion.div>}
            </AnimatePresence>
          </div>
        </motion.div>
        </div>
      </div>
      <div className={`relative z-10 flex min-h-[68px] shrink-0 items-center gap-2 border-0 border-t border-solid border-black/5 px-3 pb-3 pt-2 ${ig || tg ? "bg-white" : "bg-[#f5f3ef]"}`}>
        {wa && <span className="text-[#697b73]"><Icon name="plus" /></span>}
        <div className={`flex h-[42px] min-w-0 flex-1 items-center gap-2 rounded-full border border-solid px-3 ${ig ? "border-[#dbdbdb] bg-white" : tg ? "border-[#e1e7ec] bg-[#f3f6f8]" : "border-[#e7e3de] bg-white"}`}>
          <span className={ig ? "text-plumo-blue" : "text-[#87939c]"}><Icon name={ig ? "camera" : "smile"} /></span>
          <input readOnly tabIndex={-1} value={draft} placeholder={c.message} aria-label={c.message} className="pointer-events-none h-full w-full min-w-0 flex-1 border-0 bg-transparent p-0 font-[inherit] text-[13px] text-plumo-ink outline-none placeholder:text-[#87939c]" />
          {wa && <span className="text-[#87939c]"><Icon name="camera" /></span>}{ig && !draft && <span className="text-plumo-ink"><Icon name="mic" /></span>}
        </div>
        <motion.button type="button" aria-label={c.send} title={c.send} disabled={Boolean(sent) || !draft} onClick={() => setTick(sendAt)} animate={{ scale: !reduced && tick >= sendAt - 2 && tick < sendAt + 2 ? 0.88 : 1 }} transition={{ duration: reduced ? 0 : 0.15 }} whileTap={reduced ? undefined : { scale: 0.88 }} className={`flex size-[38px] shrink-0 cursor-pointer items-center justify-center rounded-full border-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-default ${wa ? "bg-[#128c7e] text-white" : tg ? "bg-[#3390ec] text-white" : "bg-plumo-blue text-white"}`}><Icon name="send" /></motion.button>
      </div>
    </div>
  </>;
}
