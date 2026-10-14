"use client";

import Link from "next/link";
import Image from "next/image";
import { motion, useReducedMotion } from "motion/react";
import { LanguageSwitch, useLanguage } from "@/lib/i18n";

export default function NotFound() {
  const { locale } = useLanguage();
  const reduced = useReducedMotion();
  const en = locale === "en";
  return <main className="flex min-h-svh flex-col bg-black text-white">
    <div className="flex items-center justify-between px-6 py-6 sm:px-12">
      <Link href="/" aria-label={en ? "Plumo — home" : "Plumo — главная"} className="inline-flex items-center gap-3 text-xl font-semibold tracking-tight">
        <Image src="/images/plumo-avatar.svg" alt="" width={32} height={32} />plumo
      </Link>
      <div className="[&_.language-switch_button]:text-white [&_.language-switch_button[aria-pressed=true]]:text-white"><LanguageSwitch /></div>
    </div>
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center px-6 pb-16 text-center">
      <div className="relative mb-8 flex h-48 w-48 items-center justify-center sm:h-60 sm:w-60" aria-hidden="true">
        <motion.svg viewBox="0 0 200 200" className="h-full w-full" animate={reduced ? {} : { rotate: [0, 45, 90] }} transition={{ duration: 6, repeat: Infinity, ease: "linear" }}>
          {Array.from({ length: 8 }, (_, index) => {
            const angle = index * Math.PI / 4 - Math.PI / 2;
            return <motion.circle key={index} cx={100 + Math.cos(angle) * 57} cy={100 + Math.sin(angle) * 57} r={10} fill="white"
              initial={false}
              animate={reduced ? {} : { opacity: [0, 1, 1, 0, 0], r: [2, 10, 10, 2, 2] }}
              transition={{ duration: 3.6, repeat: Infinity, delay: index * .09, times: [0, .2, .6, .8, 1], ease: "easeInOut" }} />;
          })}
        </motion.svg>
        <span className="absolute text-3xl font-medium tracking-tight">404</span>
      </div>
      <h1 className="m-0 text-3xl font-medium tracking-tight sm:text-5xl">{en ? "Page not found" : "Страница не найдена"}</h1>
      <p className="mb-8 mt-5 max-w-sm text-base leading-relaxed text-white/55">{en ? "This address leads nowhere. Let's return to Plumo." : "По этому адресу ничего нет. Давайте вернёмся к Plumo."}</p>
      <Link href="/" className="login-link button-pill">{en ? "Back to home" : "На главную"}</Link>
    </div>
    <p className="m-0 px-6 pb-6 text-center text-xs text-white/35">Plumo · {en ? "Every conversation has a next chapter." : "Каждый разговор имеет продолжение."}</p>
  </main>;
}
