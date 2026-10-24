"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Mail01Icon, ViewIcon, ViewOffIcon, UserIcon, Globe02Icon } from "@hugeicons/core-free-icons";
import { PlumoIcon } from "@/components/ui/plumo-icon";
import { accountToken, passwordIssue, registrationIssue, safeNextPath } from "@/lib/auth/registration";
import { LanguageSwitch, useLanguage } from "@/lib/i18n";

const inputClass = "h-[46px] w-full rounded-xl border border-solid border-plumo-line bg-transparent px-3.5 pr-12 font-[inherit] text-[18px] text-plumo-ink shadow-sm placeholder:text-plumo-muted focus:border-plumo-blue sm:text-[20px]";
const labelClass = "text-[17px] leading-6 text-plumo-ink";
const buttonClass = "flex min-h-[46px] w-full cursor-pointer items-center justify-center rounded-xl border border-solid border-plumo-ink bg-plumo-ink px-4 py-2 font-[inherit] text-[18px] font-medium text-white shadow-sm transition-opacity hover:opacity-85 disabled:cursor-wait disabled:opacity-60";
type Mode = "login" | "register" | "reset" | "verify" | "new-password";
type Notice = "pending" | "delivery" | "sent" | "unverified" | "resent" | "done" | null;

export function AuthScreen({ mode }: { mode: Mode }) {
  const { t, locale } = useLanguage();
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState<Notice>(null);
  const [email, setEmail] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const submitting = useRef(false);
  const tokenLoaded = useRef(false);
  const register = mode === "register";
  const verify = mode === "verify";
  const newPassword = mode === "new-password";
  const forgot = mode === "reset";

  useEffect(() => {
    if ((verify || newPassword) && !tokenLoaded.current) {
      tokenLoaded.current = true;
      setToken(accountToken(window.location.hash));
      // A token stays in component memory, never in storage, analytics URLs or server access logs.
      window.history.replaceState(null, "", window.location.pathname);
    }
    setReady(true);
  }, [verify, newPassword]);
  useEffect(() => {
    if (!cooldown) return;
    const timer = window.setTimeout(() => setCooldown(value => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  async function send(path: string, payload: unknown) {
    const response = await fetch(`/api/auth/${path}`, {
      method: "POST", headers: { "content-type": "application/json", "x-plumo-request": "1" },
      credentials: "same-origin", body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (data?.code === "email_not_verified") { setNotice("unverified"); return null; }
      throw new Error(data?.code === "invalid_account_token" ? t.linkInvalid : response.status === 409 ? t.registerConflict
        : response.status === 429 ? t.accountLimited : response.status === 422 ? t.registerInvalid
        : response.status === 401 ? t.loginWrong : data?.code === "not_configured" ? t.mailNotConfigured : t.loginOffline);
    }
    return data;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    const form = new FormData(event.currentTarget);
    const enteredEmail = String(form.get("email") ?? email).trim();
    const password = String(form.get("password") ?? "");
    const name = String(form.get("name") ?? "");
    const issue = register ? registrationIssue({ name, email: enteredEmail, password, locale }) : null;
    if (issue) { setError(issue === "name" ? t.registerName : issue === "email" ? t.registerEmail : t.registerPassword); return; }
    if (newPassword && (passwordIssue(password) || password !== form.get("confirmation"))) {
      setError(passwordIssue(password) ? t.registerPassword : t.passwordMismatch); return;
    }
    if ((newPassword || (verify && token)) && !token) { setError(t.linkInvalid); return; }
    submitting.current = true;
    setBusy(true); setError(""); setEmail(enteredEmail);
    let navigating = false;
    try {
      const path = register ? "register" : newPassword ? "reset-password" : verify && token ? "verify-email" : verify ? "resend-verification" : forgot ? "forgot-password" : "login";
      const payload = register ? { name, email: enteredEmail, password, locale } : newPassword ? { token, password }
        : verify && token ? { token } : forgot || verify ? { email: enteredEmail, locale } : { email: enteredEmail, password };
      const data = await send(path, payload);
      if (data === null) return;
      if (register) { setNotice(data.email_delivery === "sent" ? "pending" : "delivery"); setCooldown(60); }
      else if (forgot || (verify && !token)) { setNotice("sent"); setCooldown(60); }
      else if (newPassword) { setNotice("done"); setToken(null); }
      else {
        navigating = true;
        window.location.assign(verify ? "/create/wizard" : safeNextPath(new URLSearchParams(window.location.search).get("next")));
        return;
      }
    } catch (problem) { setError(problem instanceof Error ? problem.message : t.loginOffline); }
    finally { if (!navigating) { submitting.current = false; setBusy(false); } }
  }

  async function resend() {
    if (submitting.current || cooldown) return;
    submitting.current = true; setBusy(true); setError("");
    try {
      await send("resend-verification", { email, locale });
      setNotice("resent"); setCooldown(60);
    } catch (problem) { setError(problem instanceof Error ? problem.message : t.loginOffline); }
    finally { submitting.current = false; setBusy(false); }
  }

  const pending = notice === "pending" || notice === "delivery" || notice === "unverified" || notice === "resent";
  const showEmail = !newPassword && !(verify && token);
  const showPasswordField = !forgot && !verify;
  const completed = notice === "done";
  const title = verify ? t.verifyTitle : newPassword ? t.newPasswordTitle : forgot ? t.resetTitle : register ? t.registerTitle : t.loginTitle;
  const description = verify ? (token ? t.verifyDescription : t.verifyResendDescription) : newPassword ? t.newPasswordDescription : forgot ? t.resetDescription : register ? t.registerDescription : t.loginDescription;
  const invalidLink = ready && newPassword && !token && !completed;

  return <div className="min-h-svh bg-plumo-line/15 text-plumo-ink">
    <header className="flex h-[72px] items-center justify-between px-4 sm:px-8">
      <Link href="/" className="brand" aria-label={t.home}><span className="brand-crop"><Image src="/images/plumo-logo.png" alt="" width={172} height={172} priority className="brand-image mix-blend-multiply" /></span></Link>
      <details className="group relative z-10" onKeyDown={event => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
        <summary aria-label={t.language} title={t.language} className="flex size-12 cursor-pointer list-none items-center justify-center rounded-full border border-solid border-plumo-line text-plumo-muted hover:text-plumo-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-plumo-blue [&::-webkit-details-marker]:hidden"><PlumoIcon icon={Globe02Icon} size={22} /></summary>
        <div className="absolute right-0 top-14 rounded-xl border border-solid border-plumo-line bg-white p-2 shadow-sm" onClick={event => { if (event.target instanceof HTMLButtonElement && !event.target.disabled) event.currentTarget.closest("details")?.removeAttribute("open"); }}><LanguageSwitch /></div>
      </details>
    </header>
    <main className="flex min-h-[calc(100svh-72px)] items-center justify-center px-4 py-16 sm:px-6">
      <section aria-labelledby="auth-title" className="w-full max-w-[528px]">
        <h1 id="auth-title" className="m-0 text-center text-[32px] font-medium leading-tight tracking-tight">{title}</h1>
        <p className="mb-0 mt-1 text-center text-[18px] leading-relaxed text-plumo-muted">{description}</p>
        {completed ? <div className="mt-8 text-center"><p role="status">{t.passwordChanged}</p><Link href="/login" className={buttonClass}>{t.login}</Link></div> : pending ? <div className="mt-8 flex flex-col gap-5 text-center">
          <p className="m-0 leading-relaxed" role="status">{notice === "delivery" ? t.mailDeliveryFailed : notice === "unverified" ? t.verifyRequired : notice === "resent" ? t.emailRequestAccepted : t.verifySent} <strong className="break-all font-medium">{email}</strong></p>
          <button type="button" className={buttonClass} onClick={resend} disabled={busy || cooldown > 0}>{busy ? t.sendingEmail : cooldown ? `${t.resendEmail} (${cooldown})` : t.resendEmail}</button>
          <Link href="/verify-email" className="text-[14px] text-plumo-muted hover:underline">{t.useAnotherEmail}</Link>
        </div> : <form className="mt-8 flex flex-col gap-5" onSubmit={submit} aria-busy={busy} onChange={() => { if (!submitting.current) setError(""); }}>
          {notice === "sent" && <p className="m-0 text-[15px] leading-relaxed text-plumo-muted" role="status">{t.emailRequestAccepted}</p>}
          {register && <div className="flex flex-col gap-1"><label htmlFor="name" className={labelClass}>{t.name}</label><div className="relative"><input id="name" name="name" className={inputClass} autoComplete="name" required maxLength={100} placeholder={t.namePlaceholder} /><span className="pointer-events-none absolute inset-y-0 right-3.5 flex items-center"><PlumoIcon icon={UserIcon} size={22} /></span></div></div>}
          {showEmail && <div className="flex flex-col gap-1"><label htmlFor="email" className={labelClass}>{t.email}</label><div className="relative"><input id="email" name="email" className={inputClass} type="email" autoComplete="email" required maxLength={254} placeholder={t.emailPlaceholder} /><span className="pointer-events-none absolute inset-y-0 right-3.5 flex items-center"><PlumoIcon icon={Mail01Icon} size={22} /></span></div></div>}
          {showPasswordField && <div className="flex flex-col gap-1"><label htmlFor="password" className={labelClass}>{newPassword ? t.newPassword : t.password}</label><div className="relative">
            <input id="password" name="password" className={inputClass} type={showPassword ? "text" : "password"} autoComplete={register || newPassword ? "new-password" : "current-password"} placeholder={t.passwordPlaceholder} required minLength={register || newPassword ? 10 : 1} maxLength={register || newPassword ? 128 : 200} aria-describedby={register || newPassword ? "password-hint" : undefined} />
            <button type="button" className="absolute right-0 top-0 flex size-[46px] cursor-pointer items-center justify-center rounded-xl border-0 bg-transparent text-plumo-ink" aria-label={showPassword ? t.hide : t.show} aria-controls="password" aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}><PlumoIcon icon={showPassword ? ViewOffIcon : ViewIcon} size={22} /></button>
          </div>{(register || newPassword) && <span className="mt-1 text-[13px] text-plumo-muted" id="password-hint">{t.passwordHint}</span>}</div>}
          {newPassword && <div className="flex flex-col gap-1"><label htmlFor="confirmation" className={labelClass}>{t.confirmPassword}</label><input id="confirmation" name="confirmation" type={showPassword ? "text" : "password"} autoComplete="new-password" required maxLength={128} className={inputClass} /></div>}
          {mode === "login" && <p className="m-0 text-[17px] leading-6">{t.forgot}{" "}<Link href="/forgot-password" className="hover:underline">{t.recover}</Link></p>}
          {invalidLink && <p role="status" className="m-0 text-red-700">{t.linkInvalid}</p>}
          <button className={buttonClass} type="submit" disabled={busy || invalidLink || ((verify || newPassword) && !ready) || ((forgot || (verify && !token)) && cooldown > 0)}>
            {busy ? (forgot || verify ? t.sendingEmail : newPassword ? t.savingPassword : register ? t.registering : t.signingIn) : register ? t.register : newPassword ? t.savePassword : verify && token ? t.verifyAction : verify ? t.resendEmail : forgot ? t.resetAction : t.login}
            {!busy && cooldown > 0 && (forgot || (verify && !token)) ? ` (${cooldown})` : ""}
          </button>
        </form>}
        {error && <p className="mb-0 mt-4 text-center text-[14px] leading-relaxed text-red-700" role="alert">{error}</p>}
        {verify && token && error && <p className="text-center"><Link href="/verify-email" onClick={() => { setToken(null); setError(""); }} className="text-plumo-blue hover:underline">{t.resendEmail}</Link></p>}
        {newPassword && !completed && <p className="text-center"><Link href="/forgot-password" className="text-plumo-blue hover:underline">{t.requestNewLink}</Link></p>}
        {!completed && <p className="mb-0 mt-7 text-center text-[17px] leading-6">{mode === "login" ? <>{t.noAccount}{" "}<Link className="hover:underline" href="/register">{t.registerTitle}</Link></> : <Link className="hover:underline" href="/login">{t.backLogin}</Link>}</p>}
      </section>
    </main>
  </div>;
}
