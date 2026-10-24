"use client";

import Image from "next/image";
import Link from "next/link";
import { useRef, useState, type FormEvent } from "react";
import { Mail01Icon, ViewIcon, ViewOffIcon, UserIcon, Globe02Icon } from "@hugeicons/core-free-icons";
import { PlumoIcon } from "@/components/ui/plumo-icon";
import { registrationIssue, safeNextPath } from "@/lib/auth/registration";
import { LanguageSwitch, useLanguage } from "@/lib/i18n";

function AuthIcon({ type }: { type: "email" | "eye" | "eye-off" | "name" | "globe" | "google" }) {
  if (type !== "google") return <PlumoIcon size={22} icon={({ email: Mail01Icon, eye: ViewIcon, "eye-off": ViewOffIcon, name: UserIcon, globe: Globe02Icon })[type]} />;
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {type === "google" && <path fill="currentColor" stroke="none" d="M21.6 12.23c0-.71-.06-1.39-.18-2.05H12v3.88h5.38a4.6 4.6 0 0 1-2 3.02v2.51h3.24c1.9-1.75 2.98-4.33 2.98-7.36ZM12 22c2.7 0 4.96-.9 6.62-2.41l-3.24-2.51c-.9.6-2.04.96-3.38.96-2.6 0-4.81-1.75-5.6-4.11H3.06v2.59A10 10 0 0 0 12 22ZM6.4 13.93a6 6 0 0 1 0-3.86V7.48H3.06a10 10 0 0 0 0 9.04l3.34-2.59ZM12 5.96c1.47 0 2.79.5 3.82 1.49l2.87-2.87A9.6 9.6 0 0 0 12 2a10 10 0 0 0-8.94 5.48l3.34 2.59C7.19 7.71 9.4 5.96 12 5.96Z" />}
  </svg>;
}

const inputClass = "h-[46px] w-full rounded-xl border border-solid border-plumo-line bg-transparent px-3.5 pr-12 font-[inherit] text-[18px] text-plumo-ink shadow-sm placeholder:text-plumo-muted focus:border-plumo-blue sm:text-[20px]";
const labelClass = "text-[17px] leading-6 text-plumo-ink";

type Status = "form" | "google" | "signing" | "wrong" | "locked" | "offline" | "conflict" | "invalid" | "name" | "email" | "password" | "locale" | null;

// Only a same-site path is allowed after sign-in, never an external address.
function nextPath(): string {
  const value = new URLSearchParams(window.location.search).get("next") ?? "";
  return safeNextPath(value);
}

export function AuthScreen({ mode }: { mode: "login" | "register" | "reset" }) {
  const { t, locale } = useLanguage();
  const [showPassword, setShowPassword] = useState(false);
  const [status, setStatus] = useState<Status>(null);
  const submitting = useRef(false);
  const register = mode === "register";
  const reset = mode === "reset";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    if (reset) { setStatus("form"); return; }
    const form = new FormData(event.currentTarget);
    const payload = { email: String(form.get("email") ?? ""), password: String(form.get("password") ?? ""), ...(register ? { name: String(form.get("name") ?? ""), locale } : {}) };
    const issue = register ? registrationIssue(payload) : null;
    if (issue) { setStatus(issue); return; }
    submitting.current = true;
    setStatus("signing");
    try {
      const response = await fetch(`/api/auth/${register ? "register" : "login"}`, {
        method: "POST",
        headers: { "content-type": "application/json", "x-plumo-request": "1" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      if (response.ok) {
        window.location.assign(register ? "/create/wizard" : nextPath());
        return;
      }
      submitting.current = false;
      setStatus(register && response.status === 409 ? "conflict" : register && response.status === 422 ? "invalid" : response.status === 429 ? "locked" : response.status === 401 || response.status === 422 ? "wrong" : "offline");
    } catch {
      submitting.current = false;
      setStatus("offline");
    }
  }
  const message = status === "google" ? t.googleUnavailable : status === "form" ? (reset ? t.resetUnavailable : t.unavailable)
    : status === "conflict" ? t.registerConflict : status === "invalid" || status === "locale" ? t.registerInvalid : status === "name" ? t.registerName : status === "email" ? t.registerEmail : status === "password" ? t.registerPassword
    : status === "wrong" ? t.loginWrong : status === "locked" ? (register ? t.registerLimited : t.loginLocked) : status === "offline" ? t.loginOffline : "";

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
        <form className="mt-8 flex flex-col gap-5" onSubmit={submit} onChange={() => { if (!submitting.current) setStatus(null); }} aria-busy={status === "signing"}>
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
                placeholder={t.passwordPlaceholder} required minLength={register ? 10 : 1} maxLength={register ? 128 : 200} aria-describedby={register ? "password-hint" : undefined} />
              <button type="button" className="absolute right-0 top-0 flex size-[46px] cursor-pointer items-center justify-center rounded-xl border-0 bg-transparent text-plumo-ink" aria-label={showPassword ? t.hide : t.show} aria-controls="password" aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}><AuthIcon type={showPassword ? "eye-off" : "eye"} /></button>
            </div>
            {register && <span className="mt-1 text-[13px] text-plumo-muted" id="password-hint">{t.passwordHint}</span>}
          </div>}
          {mode === "login" && <p className="m-0 text-[17px] leading-6">{t.forgot}{" "}<Link className="hover:underline hover:underline-offset-4" href="/forgot-password">{t.recover}</Link></p>}
          <button className="flex min-h-[46px] w-full cursor-pointer items-center justify-center rounded-xl border border-solid border-plumo-ink bg-plumo-ink px-4 py-2 font-[inherit] text-[18px] font-medium text-white shadow-sm transition-opacity hover:opacity-85 disabled:cursor-wait disabled:opacity-60" type="submit" disabled={status === "signing"}>{status === "signing" ? (register ? t.registering : t.signingIn) : reset ? t.resetAction : register ? t.register : t.login}</button>
        </form>
        {reset ? <p className="mb-0 mt-7 text-center text-[17px]"><Link className="hover:underline hover:underline-offset-4" href="/login">{t.backLogin}</Link></p> : <>
          <p className="mb-0 mt-7 text-center text-[17px] leading-6">{register ? t.hasAccount : t.noAccount}{" "}<Link className="hover:underline hover:underline-offset-4" href={register ? "/login" : "/register"}>{register ? t.login : t.registerTitle}</Link></p>
          <div className="my-7 flex items-center gap-3 text-[14px] uppercase text-plumo-muted"><span className="h-px flex-1 bg-plumo-line" /><span>{t.or}</span><span className="h-px flex-1 bg-plumo-line" /></div>
          <button type="button" disabled={status === "signing"} onClick={() => setStatus("google")} className="flex min-h-[46px] w-full cursor-pointer items-center justify-center gap-4 rounded-xl border border-solid border-plumo-line bg-white px-4 py-2 font-[inherit] text-[18px] text-plumo-ink shadow-sm transition-colors hover:bg-plumo-line/25"><AuthIcon type="google" />{t.googleLogin}</button>
        </>}
        <p className={`mb-0 mt-4 text-center text-[13px] leading-relaxed empty:hidden ${status && !["form", "google", "signing"].includes(status) ? "text-red-700" : "text-plumo-muted"}`} role="status" aria-live="polite">{message}</p>
        {!reset && <p className="mb-0 mt-5 text-center text-[13px] text-plumo-muted"><Link href="/dashboard" className="hover:text-plumo-blue hover:underline hover:underline-offset-4">{locale === "en" ? "Open workspace" : "Открыть кабинет"}</Link></p>}
      </section>
    </main>
  </div>;
}
