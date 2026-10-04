"use client";

import Image from "next/image";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { LanguageSwitch, useLanguage } from "@/lib/i18n";

export function AuthScreen({ mode }: { mode: "login" | "register" | "reset" }) {
  const { t } = useLanguage();
  const [showPassword, setShowPassword] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const register = mode === "register";
  const reset = mode === "reset";
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // UI only: never persist or transmit credentials before a backend exists.
    setSubmitted(true);
  }
  return <div className="auth-page">
    <div className="auth-topbar">
      <Link href="/" className="brand" aria-label={t.home}>
        <span className="brand-crop"><Image src="/images/plumo-logo.png" alt="" width={172} height={172} priority className="brand-image" /></span>
      </Link>
      <LanguageSwitch />
    </div>
    <main className="auth-main">
      <div className="auth-panel">
        <h1>{reset ? t.resetTitle : register ? t.registerTitle : t.loginTitle}</h1>
        <p className="auth-subtitle">{reset ? t.resetDescription : <>{register ? t.hasAccount : t.noAccount}{" "}<Link href={register ? "/login" : "/register"}>{register ? t.login : t.register}</Link></>}</p>
        <form className="auth-form" onSubmit={submit} onChange={() => setSubmitted(false)}>
          {register && <div className="auth-field"><label htmlFor="name">{t.name}</label><input id="name" name="name" autoComplete="name" placeholder={t.namePlaceholder} required maxLength={100} /></div>}
          <div className="auth-field"><label htmlFor="email">{t.email}</label><input id="email" name="email" type="email" autoComplete="email" placeholder="you@example.com" required maxLength={254} /></div>
          {!reset && <div className="auth-field"><label htmlFor="password">{t.password}</label>
            <div className="password-input"><input id="password" name="password" type={showPassword ? "text" : "password"} autoComplete={register ? "new-password" : "current-password"}
              placeholder="••••••••" required minLength={register ? 8 : 1} maxLength={128} aria-describedby={register ? "password-hint" : undefined} />
              <button type="button" className="password-toggle" aria-controls="password" aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)}>{showPassword ? t.hide : t.show}</button>
            </div>
            {register && <span className="password-hint" id="password-hint">{t.passwordHint}</span>}
          </div>}
          {mode === "login" && <Link className="forgot-link" href="/forgot-password">{t.forgot}</Link>}
          <button className="auth-submit" type="submit">{reset ? t.resetAction : register ? t.register : t.login}<span aria-hidden="true">→</span></button>
          <p className="auth-status" role="status" aria-live="polite">{submitted ? (reset ? t.resetUnavailable : t.unavailable) : ""}</p>
        </form>
        {reset && <Link className="auth-back" href="/login">← {t.backLogin}</Link>}
      </div>
    </main>
  </div>;
}
