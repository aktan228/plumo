"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useLanguage } from "@/lib/i18n";
import samples from "./voice-demo-data.json";
import "./voice-call-demo.css";

const copy = {
  ru: {
    title: "Не каждый клиент пишет.", accent: "Некоторые звонят.",
    description: "Услышать запрос. Уточнить детали. Дать вашей команде контекст для следующего шага.",
    incoming: "Входящий звонок", client: "Клиент", name: "Айдана", assistant: "Голосовой ассистент",
    listen: "Послушать разговор", pause: "Пауза", resume: "Продолжить", replay: "Послушать ещё раз",
    ready: "Plumo на связи", playing: "Разговор идёт", paused: "На паузе", ended: "Разговор завершён",
    waiting: "Один звонок. Вся суть.", waitingBody: "Клиент расскажет, что ищет. Plumo уточнит детали — вы увидите, что останется для менеджера.",
    transcript: "Сейчас в разговоре", summary: "Контекст для менеджера", summaryTitle: "Теперь можно продолжить.",
    need: "Ищет", needValue: "Двухкомнатную квартиру для семьи",
    preferences: "Важно", preferencesValue: "Юг города · школа рядом",
    budget: "Бюджет", budgetValue: "До 8 000 000 сом",
    time: "Желаемое время", timeValue: "Суббота, после 14:00",
    next: "Следующий шаг", nextValue: "Проверить варианты и время просмотра. Перезвонить клиенту.",
    notBooked: "Время просмотра ещё не подтверждено.", full: "Прочитать весь разговор",
    disclosure: "Сценарный аудиопример с вымышленными данными. Телефония не подключена.",
    error: "Аудио не удалось воспроизвести. Попробуйте ещё раз или прочитайте разговор ниже.",
    soundOn: "Выключить звук", soundOff: "Включить звук", loading: "Загружаем аудио…",
  },
  en: {
    title: "Not every customer texts.", accent: "Some call.",
    description: "Hear the request. Ask the right questions. Give your team the context to take it further.",
    incoming: "Incoming call", client: "Customer", name: "Aidana", assistant: "Voice assistant",
    listen: "Listen to the call", pause: "Pause", resume: "Continue", replay: "Listen again",
    ready: "Plumo is here", playing: "Call in progress", paused: "Paused", ended: "Call ended",
    waiting: "One call. The whole picture.", waitingBody: "The customer shares what they need. Plumo asks for the details. See what your manager can pick up next.",
    transcript: "In the conversation", summary: "Context for the manager", summaryTitle: "Ready for the next step.",
    need: "Looking for", needValue: "A two-bedroom family apartment",
    preferences: "Priorities", preferencesValue: "South of the city · school nearby",
    budget: "Budget", budgetValue: "Up to 8,000,000 soms",
    time: "Preferred time", timeValue: "Saturday, after 2 pm",
    next: "Next step", nextValue: "Check suitable properties and viewing times. Call the customer back.",
    notBooked: "The viewing time is not confirmed yet.", full: "Read the full conversation",
    disclosure: "Scripted audio with fictional data. No telephony is connected.",
    error: "Audio could not play. Try again or read the conversation below.",
    soundOn: "Mute", soundOff: "Unmute", loading: "Loading audio…",
  },
};

function Icon({ type, className = "" }: { type: "phone" | "play" | "pause" | "replay" | "sound" | "muted"; className?: string }) {
  return <svg className={className} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {type === "phone" ? <path d="M5 3h4l2 5-3 2a15 15 0 0 0 6 6l2-3 5 2v4a2 2 0 0 1-2 2C9 21 3 15 3 5a2 2 0 0 1 2-2Z" /> :
      type === "play" ? <path d="m9 5 11 7-11 7Z" fill="currentColor" stroke="none" /> :
      type === "pause" ? <><path d="M8 5v14M16 5v14" strokeWidth="3" /></> :
      type === "replay" ? <><path d="M3 10a9 9 0 1 1 2 8M3 4v6h6" /></> :
      <><path d="M11 4 6 8H3v8h3l5 4Z" />{type === "sound" ? <><path d="M15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14" /></> : <path d="m16 9 5 6m0-6-5 6" />}</>}
  </svg>;
}

function clock(seconds: number) {
  const value = Math.floor(seconds);
  return `${Math.floor(value / 60).toString().padStart(2, "0")}:${(value % 60).toString().padStart(2, "0")}`;
}

function CallPlayer({ locale }: { locale: "ru" | "en" }) {
  const c = copy[locale];
  const sample = samples[locale];
  const reduced = useReducedMotion();
  const audioRef = useRef<HTMLAudioElement>(null);
  const sectionRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"idle" | "playing" | "paused" | "ended">("idle");
  const [elapsed, setElapsed] = useState(0);
  const [muted, setMuted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const activeIndex = Math.max(0, sample.cues.findLastIndex(cue => elapsed >= cue.start));
  const cue = sample.cues[activeIndex];
  const isPlaying = status === "playing";
  const finished = status === "ended";
  const started = status !== "idle";
  const label = loading ? c.loading : isPlaying ? c.pause : finished ? c.replay : started ? c.resume : c.listen;

  useEffect(() => {
    const audio = audioRef.current;
    const pause = () => { if (audio && !audio.paused) audio.pause(); };
    const onVisibility = () => { if (document.hidden) pause(); };
    const observer = new IntersectionObserver(entries => {
      if (!entries[0].isIntersecting) pause();
    });
    if (sectionRef.current) observer.observe(sectionRef.current);
    document.addEventListener("visibilitychange", onVisibility);
    return () => { observer.disconnect(); document.removeEventListener("visibilitychange", onVisibility); pause(); };
  }, []);

  async function togglePlayback() {
    const audio = audioRef.current;
    if (!audio) return;
    if (!audio.paused) { audio.pause(); return; }
    if (finished) { audio.currentTime = 0; setElapsed(0); }
    setError(false);
    setLoading(true);
    try { await audio.play(); }
    catch (cause) {
      if (!(cause instanceof DOMException && cause.name === "AbortError")) setError(true);
    } finally { setLoading(false); }
  }

  const transition = { duration: reduced ? 0 : 0.35 };
  return <div ref={sectionRef} className="mt-12 md:mt-16">
    <audio ref={audioRef} src={`/audio/voice-demo/${locale}.mp3`} preload="none" muted={muted}
      onTimeUpdate={event => setElapsed(event.currentTarget.currentTime)}
      onPlay={() => setStatus("playing")}
      onPause={event => { if (!event.currentTarget.ended) setStatus(value => value === "idle" ? "idle" : "paused"); }}
      onEnded={() => { setStatus("ended"); setElapsed(sample.duration); }}
      onWaiting={() => setLoading(true)} onPlaying={() => setLoading(false)}
      onError={() => { setError(true); setLoading(false); }} />
    <div className="grid overflow-hidden rounded-[32px] bg-plumo-soft lg:grid-cols-[1.05fr_1fr]">
      <div className="relative flex min-h-[490px] flex-col overflow-hidden bg-[#09090b] px-6 py-7 text-white md:px-10 md:py-9 lg:min-h-[550px]">
        <div className="flex items-center justify-between gap-4 text-[12px] text-[#a3a3ae]">
          <span className="flex items-center gap-2"><Icon type="phone" className="h-4 w-4 text-plumo-blue" />{c.incoming}</span>
          <span className="font-mono tabular-nums">{clock(elapsed)} <span className="text-[#62626e]">/ {clock(sample.duration)}</span></span>
        </div>
        <div className="relative flex flex-1 flex-col items-center justify-center py-10">
          <div className="absolute left-1/2 top-1/2 h-[260px] w-[260px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/[0.04]" aria-hidden="true" />
          <div className="absolute left-1/2 top-1/2 h-[360px] w-[360px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/[0.03]" aria-hidden="true" />
          <div className="relative flex h-[94px] w-[94px] items-center justify-center rounded-[28px] bg-[#17171b] ring-1 ring-white/10">
            {/* Existing white brand mark; no raster background. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/images/plumo-avatar.svg" width="52" height="52" alt="Plumo" />
          </div>
          <p className="relative mb-0 mt-5 text-[27px] font-medium tracking-[-0.04em]">Plumo</p>
          <p className="relative mb-0 mt-1 text-[13px] text-[#92929f]">{c.assistant}</p>
          <div className="voice-demo-wave relative mt-7 flex h-12 items-center justify-center gap-[4px]" data-playing={isPlaying && !loading} aria-hidden="true">
            {Array.from({ length: 35 }, (_, index) => <span key={index} className="w-[4px] rounded-full bg-plumo-blue" style={{ height: `${8 + Math.round(Math.abs(Math.sin(index * 1.7)) * (24 + 12 * Math.sin(index * 0.23)))}px`, animationDelay: `${index * -0.13}s`, animationDuration: `${0.6 + (index % 5) * 0.12}s` }} />)}
          </div>
          <p className="relative mb-0 mt-3 text-[12px] text-[#a3a3ae]" role="status">{finished ? c.ended : isPlaying ? c.playing : started ? c.paused : c.ready}</p>
        </div>
        <div className="relative flex items-center gap-3">
          <button type="button" onClick={togglePlayback} disabled={loading} className="flex min-h-[54px] flex-1 items-center justify-center gap-3 rounded-full border-0 bg-plumo-blue px-4 text-[14px] font-medium text-white transition duration-300 hover:bg-[#4167ff] active:scale-[0.98] disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white">
            <Icon type={isPlaying ? "pause" : finished ? "replay" : "play"} />{label}
          </button>
          <button type="button" aria-label={muted ? c.soundOff : c.soundOn} aria-pressed={muted} onClick={() => setMuted(value => !value)} className="flex h-[54px] w-[54px] shrink-0 items-center justify-center rounded-full border border-[#303037] bg-transparent text-white transition hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"><Icon type={muted ? "muted" : "sound"} /></button>
        </div>
        <div className="relative mt-5 h-[2px] overflow-hidden rounded-full bg-white/10" aria-hidden="true"><div className="h-full bg-plumo-blue transition-[width] duration-200" style={{ width: `${Math.min(100, elapsed / sample.duration * 100)}%` }} /></div>
        {error && <p className="mb-0 mt-4 text-[12px] leading-relaxed text-[#ffc6c6]" role="alert">{c.error}</p>}
      </div>
      <div className="flex min-h-[410px] flex-col p-6 md:p-10">
        <div className="flex items-center gap-3 border-b border-plumo-line pb-5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/images/customer-pixel-girl.png" width="42" height="42" alt="" className="h-[42px] w-[42px] rounded-full" />
          <div><p className="m-0 text-[14px] font-semibold">{c.name}</p><p className="mb-0 mt-1 text-[11px] text-plumo-muted">{c.client}</p></div>
        </div>
        <AnimatePresence mode="wait" initial={false}>
          {finished ? <motion.div key="summary" initial={{ opacity: 0, y: reduced ? 0 : 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={transition} className="pt-7">
            <p className="m-0 text-[11px] text-plumo-blue">{c.summary}</p>
            <h3 className="!mb-5 !mt-3 !text-[25px] !font-semibold !leading-tight !tracking-[-0.04em]">{c.summaryTitle}</h3>
            <dl className="m-0 space-y-0">{[[c.need, c.needValue], [c.preferences, c.preferencesValue], [c.budget, c.budgetValue], [c.time, c.timeValue]].map(([name, value]) => <div key={name} className="grid grid-cols-[105px_1fr] gap-3 border-b border-plumo-line py-3 text-[12px] leading-relaxed"><dt className="text-plumo-muted">{name}</dt><dd className="m-0">{value}</dd></div>)}</dl>
            <p className="mb-1 mt-5 text-[11px] text-plumo-muted">{c.next}</p><p className="m-0 text-[13px] leading-relaxed">{c.nextValue}</p><p className="mb-0 mt-3 text-[11px] text-plumo-muted">{c.notBooked}</p>
          </motion.div> : !started ? <motion.div key="intro" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={transition} className="flex flex-1 flex-col justify-center py-8">
            <span className="text-[12px] text-plumo-blue">01 — 02 — 03</span>
            <h3 className="!mb-4 !mt-5 !max-w-[360px] !text-[clamp(30px,3.2vw,44px)] !font-semibold !leading-[1.06] !tracking-[-0.05em]">{c.waiting}</h3>
            <p className="m-0 max-w-[340px] text-[14px] leading-[1.8] text-plumo-muted">{c.waitingBody}</p>
          </motion.div> : <motion.div key="transcript" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={transition} className="flex flex-1 flex-col justify-center py-8">
            <p className="mb-6 mt-0 text-[11px] text-plumo-muted">{c.transcript}</p>
            <AnimatePresence mode="wait" initial={false}><motion.div key={activeIndex} initial={{ opacity: 0, y: reduced ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={transition}>
              <p className="m-0 flex items-center gap-2 text-[12px] font-semibold text-plumo-blue"><span className="h-[6px] w-[6px] rounded-full bg-current" />{cue.speaker === "plumo" ? "Plumo" : c.name}</p>
              <p className="mb-0 mt-4 text-[clamp(21px,2.2vw,28px)] leading-[1.45] tracking-[-0.03em]">{cue.text}</p>
            </motion.div></AnimatePresence>
          </motion.div>}
        </AnimatePresence>
      </div>
    </div>
    <details className="group mx-auto mt-6 max-w-[820px] rounded-[20px] border border-plumo-line px-5 py-4 text-[12px]">
      <summary className="cursor-pointer font-medium focus-visible:outline-2 focus-visible:outline-plumo-blue">{c.full}</summary>
      <ol className="mb-0 mt-5 list-none space-y-5 p-0">{sample.cues.map((line, index) => <li key={index}><p className="mb-1 mt-0 text-[11px] text-plumo-muted">{clock(line.start)} · {line.speaker === "plumo" ? "Plumo" : c.name}</p><p className="m-0 text-[14px] leading-relaxed">{line.text}</p></li>)}</ol>
    </details>
    <p className="mb-0 mt-5 text-center text-[11px] leading-relaxed text-plumo-muted">{c.disclosure}</p>
  </div>;
}

export function VoiceCallDemo() {
  const { locale } = useLanguage();
  const c = copy[locale];
  return <section id="voice-demo" aria-labelledby="voice-demo-title" className="mx-auto max-w-[1440px] px-6 py-20 text-plumo-ink md:px-8 md:py-28 lg:px-16">
    <div className="mx-auto max-w-[980px] text-center">
      <h2 id="voice-demo-title" className="!m-0 !text-[clamp(40px,5.7vw,76px)] !font-bold !leading-[1.04] !tracking-[-0.055em]">{c.title}<br /><span className="text-plumo-blue">{c.accent}</span></h2>
      <p className="mx-auto mb-0 mt-6 max-w-[510px] text-[15px] leading-relaxed text-plumo-muted">{c.description}</p>
    </div>
    <CallPlayer key={locale} locale={locale} />
  </section>;
}
