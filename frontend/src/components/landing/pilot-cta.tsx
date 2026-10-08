"use client";

import type { CSSProperties } from "react";
import { useLanguage } from "@/lib/i18n";

const copy = {
  ru: { title: "Ваш бизнес на связи.", subtitle: "Даже когда вас нет.", action: "Записаться на демо" },
  en: { title: "Your business stays connected.", subtitle: "Even when you’re away.", action: "Book a demo" },
};
const buttonTheme = { "--button-base": "#fff", "--button-ink": "#111113", "--button-wave": "#2b55ff", "--button-hover-ink": "#fff" } as CSSProperties;

export function PilotCTA({ onDemo }: { onDemo: () => void }) {
  const { locale } = useLanguage();
  const c = copy[locale];
  return <section id="pilot" aria-labelledby="pilot-title" className="bg-[#0a0a0a] px-6 py-20 text-white md:px-8 md:py-24 lg:px-16">
    <div className="mx-auto max-w-[1200px] text-center">
      <h2 id="pilot-title" className="!m-0 !text-[clamp(32px,4.5vw,62px)] !font-medium !leading-[1.15] !tracking-[-0.045em]">{c.title}<br /><span className="text-[#85858e]">{c.subtitle}</span></h2>
      <button type="button" aria-haspopup="dialog" onClick={onDemo} style={buttonTheme} className="login-link button-pill mx-auto mt-10 !min-h-[52px] cursor-pointer !border-white !px-7 !py-4 font-[inherit] !text-[14px] !font-medium focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-plumo-blue">{c.action}</button>
    </div>
  </section>;
}
