"use client";

import Image from "next/image";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { LanguageSwitch, useLanguage } from "@/lib/i18n";

function AuthIcon({ type }: { type: "email" | "eye" | "eye-off" | "name" | "globe" | "google" }) {
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {type === "email" && <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 6 9 7 9-7" /></>}
    {(type === "eye" || type === "eye-off") && <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" />{type === "eye-off" && <path d="m3 3 18 18" />}</>}
    {type === "name" && <><circle cx="12" cy="8" r="4" /><path d="M4 21v-2a8 8 0 0 1 16 0v2" /></>}
    {type === "globe" && <><circle cx="12" cy="12" r="9" /><ellipse cx="12" cy="12" rx="4" ry="9" /><path d="M3 12h18" /></>}
    {type === "google" && <path fill="currentColor" stroke="none" d="M21.6 12.23c0-.71-.06-1.39-.18-2.05H12v3.88h5.38a4.6 4.6 0 0 1-2 3.02v2.51h3.24c1.9-1.75 2.98-4.33 2.98-7.36ZM12 22c2.7 0 4.96-.9 6.62-2.41l-3.24-2.51c-.9.6-2.04.96-3.38.96-2.6 0-4.81-1.75-5.6-4.11H3.06v2.59A10 10 0 0 0 12 22ZM6.4 13.93a6 6 0 0 1 0-3.86V7.48H3.06a10 10 0 0 0 0 9.04l3.34-2.59ZM12 5.96c1.47 0 2.79.5 3.82 1.49l2.87-2.87A9.6 9.6 0 0 0 12 2a10 10 0 0 0-8.94 5.48l3.34 2.59C7.19 7.71 9.4 5.96 12 5.96Z" />}
  </svg>;
}

const inputClass = "h-[46px] w-full rounded-xl border border-solid border-plumo-line bg-transparent px-3.5 pr-12 font-[inherit] text-[18px] text-plumo-ink shadow-sm placeholder:text-plumo-muted focus:border-plumo-blue sm:text-[20px]";
const labelClass = "text-[17px] leading-6 text-plumo-ink";

export function AuthScreen({ mode }: { mode: "login" | "register" | "reset" }) {
  const { t, locale } = useLanguage();
  const [showPassword, setShowPassword] = useState(false);
  const [status, setStatus] = useState<"form" | "google" | null>(null);
  const register = mode === "register";
  const reset = mode === "reset";

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // UI only: never persist or transmit credentials before a backend exists.
    setStatus("form");
  }

  return <div className="min-h-svh bg-plumo-line/15 text-plumo-ink">
    <header className="flex h-[72px] items-center justify-between px-4 sm:px-8">
      <Link href="/" className="brand" aria-label={t.home}>
        <span className="brand-crop"><Image src="/images/plumo-logo.png" alt="" width={172} height={172} priority className="brand-image mix-blend-multiply" /></span>
      </Link>
      <details className="group relative z-10" onKeyDown={event => {
        if (event.key === "Escape") {
          event.currentTarget.open = false;
          event.currentTarget.querySelector("summary")?.focus();
        }
      }}>
        <summary aria-label={t.language} title={t.language} className="flex size-12 cursor-pointer list-none items-center justify-center rounded-full border border-solid border-plumo-line text-plumo-muted hover:text-plumo-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-plumo-blue [&::-webkit-details-marker]:hidden"><AuthIcon type="globe" /></summary>
        <div className="absolute right-0 top-14 rounded-xl border border-solid border-plumo-line bg-white p-2 shadow-sm" onClick={event => {
          if (event.target instanceof HTMLButtonElement && !event.target.disabled) event.currentTarget.closest("details")?.removeAttribute("open");
        }}><LanguageSwitch /></div>
      </details>
    </header>
    <main className="flex min-h-[calc(100svh-72px)] items-center justify-center px-4 py-16 sm:px-6">
      <section aria-labelledby="auth-title" className="w-full max-w-[528px]">
        <h1 id="auth-title" className="m-0 text-center text-[32px] font-medium leading-tight tracking-tight">{reset ? t.resetTitle : register ? t.registerTitle : t.loginTitle}</h1>
        <p className="mb-0 mt-1 text-center text-[18px] leading-relaxed text-plumo-muted">{reset ? t.resetDescription : register ? t.registerDescription : t.loginDescription}</p>
        <form className="mt-8 flex flex-col gap-5" onSubmit={submit} onChange={() => setStatus(null)}>
          {register && <div className="flex flex-col gap-1">
            <label htmlFor="name" className={labelClass}>{t.name}</label>
            <div className="relative"><input id="name" name="name" className={inputClass} autoComplete="name" placeholder={t.namePlaceholder} required maxLength={100} /><span className="pointer-events-none absolute inset-y-0 right-3.5 flex items-center"><AuthIcon type="name" /></span></div>
          </div>}
          <div className="flex flex-col gap-1">
            <label htmlFor="email" className={labelClass}>{t.email}</label>
            <div className="relative"><input id="email" name="email" className={inputClass} type="email" autoComplete="email" placeholder={t.emailPlaceholder} required maxLength={254} /><span className="pointer-events-none absolute inset-y-0 right-3.5 flex items-center"><AuthIcon type="email" /></span></div>
          </div>
          {!reset && <div className="flex flex-col gap-1">
            <label htmlFor="password" className={labelClass}>{t.password}</label>
            <div className="relative">
              <input id="password" name="password" className={inputClass} type={showPassword ? "text" : "password"} autoComplete={register ? "new-password" : "current-password"}
                placeholder={t.passwordPlaceholder} required minLength={register ? 8 : 1} maxLength={128} aria-describedby={register ? "password-hint" : undefined} />
              <button type="button" className="absolute right-0 top-0 flex size-[46px] cursor-pointer items-center justify-center rounded-xl border-0 bg-transparent text-plumo-ink" aria-label={showPassword ? t.hide : t.show} aria-controls="password" aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}><AuthIcon type={showPassword ? "eye-off" : "eye"} /></button>
            </div>
            {register && <span className="mt-1 text-[13px] text-plumo-muted" id="password-hint">{t.passwordHint}</span>}
          </div>}
          {mode === "login" && <p className="m-0 text-[17px] leading-6">{t.forgot}{" "}<Link className="hover:underline hover:underline-offset-4" href="/forgot-password">{t.recover}</Link></p>}
          <button className="flex min-h-[46px] w-full cursor-pointer items-center justify-center rounded-xl border border-solid border-plumo-ink bg-plumo-ink px-4 py-2 font-[inherit] text-[18px] font-medium text-white shadow-sm transition-opacity hover:opacity-85" type="submit">{reset ? t.resetAction : register ? t.register : t.login}</button>
        </form>
        {reset ? <p className="mb-0 mt-7 text-center text-[17px]"><Link className="hover:underline hover:underline-offset-4" href="/login">{t.backLogin}</Link></p> : <>
          <p className="mb-0 mt-7 text-center text-[17px] leading-6">{register ? t.hasAccount : t.noAccount}{" "}<Link className="hover:underline hover:underline-offset-4" href={register ? "/login" : "/register"}>{register ? t.login : t.registerTitle}</Link></p>
          <div className="my-7 flex items-center gap-3 text-[14px] uppercase text-plumo-muted"><span className="h-px flex-1 bg-plumo-line" /><span>{t.or}</span><span className="h-px flex-1 bg-plumo-line" /></div>
          <button type="button" onClick={() => setStatus("google")} className="flex min-h-[46px] w-full cursor-pointer items-center justify-center gap-4 rounded-xl border border-solid border-plumo-line bg-white px-4 py-2 font-[inherit] text-[18px] text-plumo-ink shadow-sm transition-colors hover:bg-plumo-line/25"><AuthIcon type="google" />{t.googleLogin}</button>
        </>}
        <p className="mb-0 mt-4 text-center text-[13px] leading-relaxed text-plumo-muted empty:hidden" role="status" aria-live="polite">{status === "google" ? t.googleUnavailable : status === "form" ? (reset ? t.resetUnavailable : t.unavailable) : ""}</p>
        {!reset && <p className="mb-0 mt-5 text-center text-[13px] text-plumo-muted"><Link href="/dashboard" className="hover:text-plumo-blue hover:underline hover:underline-offset-4">{locale === "en" ? "Open workspace" : "Открыть кабинет"}</Link></p>}
      </section>
    </main>
  </div>;
}
