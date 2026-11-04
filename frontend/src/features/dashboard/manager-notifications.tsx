"use client";

import { useCallback, useState } from "react";
import Alert02Icon from "@hugeicons/core-free-icons/Alert02Icon";
import LinkSquare02Icon from "@hugeicons/core-free-icons/LinkSquare02Icon";
import Loading03Icon from "@hugeicons/core-free-icons/Loading03Icon";
import Notification01Icon from "@hugeicons/core-free-icons/Notification01Icon";
import { PlumoIcon } from "@/components/ui/plumo-icon";
import { ApiError, api, goToLogin } from "@/lib/api/client";
import type { ManagerConfirm, ManagerLink, ManagerNotifications as ManagerState } from "@/lib/api/types";
import { usePolling } from "@/lib/api/use-polling";
import { useLanguage } from "@/lib/i18n";
import { apiErrorText } from "./api-messages";
import { formatTime } from "./dialogue-model";
import { isChangingManager, managerExplanation, managerStatusLabel, managerStatusTone } from "./manager-notifications-model";

const copy = {
  ru: {
    title: "Уведомления менеджеру", lead: "Когда клиенту нужен человек, служебный бот Plumo пишет менеджеру в личный Telegram.",
    newLink: "Получить ссылку для менеджера", anotherLink: "Привязать другого менеджера", freshLink: "Новая ссылка",
    linkHint: "Ссылка показывается один раз. Если она не открывается, менеджер может отправить боту команду:",
    openBot: "Открыть бота", candidate: "Прислал код", recipient: "Получатель", confirm: "Подтвердить этот чат",
    disconnect: "Отключить уведомления", confirmDisconnect: "Отключить? Менеджер перестанет получать уведомления в Telegram.", yes: "Да, отключить", no: "Отмена",
    sent: "Чат подтверждён, контрольное сообщение отправлено.", failed: "Чат подтверждён, но контрольное сообщение не ушло: Telegram недоступен. Уведомления будут отправляться с повторами.",
    rejected: "Чат подтверждён, но Telegram отклонил сообщение. Попросите менеджера открыть бота и нажать «Запустить».",
    changing: "Пока новый чат не подтверждён, уведомления получает текущий менеджер.",
    noBot: "Служебный бот не настроен на сервере (TELEGRAM_BOT_TOKEN).", loadError: "Не удалось загрузить настройки уведомлений.", expires: "Код действует до",
  },
  en: {
    title: "Manager notifications", lead: "When a customer needs a person, the Plumo service bot messages the manager in a private Telegram chat.",
    newLink: "Get a link for the manager", anotherLink: "Bind another manager", freshLink: "New link",
    linkHint: "The link is shown once. If it does not open, the manager can send the bot this command:",
    openBot: "Open bot", candidate: "Sent the code", recipient: "Recipient", confirm: "Confirm this chat",
    disconnect: "Turn notifications off", confirmDisconnect: "Turn off? The manager will stop getting Telegram notifications.", yes: "Yes, turn off", no: "Cancel",
    sent: "Chat confirmed, control message sent.", failed: "Chat confirmed, but the control message did not go out: Telegram is unavailable. Notifications are retried.",
    rejected: "Chat confirmed, but Telegram refused the message. Ask the manager to open the bot and press Start.",
    changing: "Until the new chat is confirmed, the current manager keeps getting notifications.",
    noBot: "The service bot is not configured on the server (TELEGRAM_BOT_TOKEN).", loadError: "Could not load notification settings.", expires: "Code valid until",
  },
};

const primary = "inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 rounded-lg border-0 bg-plumo-blue px-4 py-2.5 font-[inherit] text-sm font-medium text-white transition-colors hover:bg-plumo-blue/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-not-allowed disabled:bg-plumo-line disabled:text-plumo-muted";
const secondary = "inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 rounded-lg border border-solid border-plumo-line bg-white px-4 py-2.5 font-[inherit] text-sm text-plumo-ink hover:bg-plumo-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-not-allowed disabled:opacity-60";
const tones = { ok: "bg-emerald-50 text-emerald-700", warn: "bg-amber-50 text-amber-700", error: "bg-red-50 text-red-700", idle: "bg-plumo-line/60 text-plumo-muted" };

export function ManagerNotifications() {
  const { locale } = useLanguage();
  const c = copy[locale];
  const [state, setState] = useState<ManagerState | null>(null);
  const [link, setLink] = useState<ManagerLink | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const result = await api<ManagerState>("manager-notifications", { signal });
      setState(result);
      setLoadError(false);
      // The code was used or expired: the one-time link is no longer useful.
      if (result.status !== "waiting_code") setLink(null);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.unauthenticated) goToLogin();
        setLoadError(true);
      }
      throw error;
    }
  }, []);
  // The manager presses Start in Telegram while this page is open: poll a little faster than integrations.
  const refresh = usePolling(load, 5_000, "manager-notifications");

  async function run<T>(key: string, action: () => Promise<T>, after?: (result: T) => void) {
    setBusy(key);
    setNotice(null);
    try {
      const result = await action();
      after?.(result);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.unauthenticated) goToLogin();
        setNotice({ tone: "error", text: apiErrorText(error.code, locale, error.message) });
      }
    } finally {
      setBusy(null);
      refresh();
    }
  }

  const issue = () => run("link", () => api<ManagerLink>("manager-notifications/link", { method: "POST" }), result => { setLink(result); setState(result); });
  const confirm = () => run("confirm", () => api<ManagerConfirm>("manager-notifications/confirm", { method: "POST" }), result => {
    setState(result);
    setNotice({ tone: result.control_delivery === "sent" ? "ok" : "error", text: c[result.control_delivery] });
  });
  const disconnect = () => run("disconnect", () => api<ManagerState>("manager-notifications/disconnect", { method: "POST" }), result => { setState(result); setLink(null); setConfirming(false); });

  const status = state?.status ?? "not_configured";
  const spinner = (key: string) => busy === key && <PlumoIcon icon={Loading03Icon} size={16} className="animate-spin" />;

  return <section aria-labelledby="manager-notifications-title" className="mt-8 rounded-2xl border border-solid border-plumo-line bg-white p-6">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-plumo-soft text-plumo-blue"><PlumoIcon icon={Notification01Icon} size={20} /></span>
        <div><h2 id="manager-notifications-title" className="m-0 text-lg font-semibold">{c.title}</h2><p className="mb-0 mt-1 max-w-[640px] text-sm leading-6 text-plumo-muted">{c.lead}</p></div>
      </div>
      {state && <span className={`rounded-md px-2 py-1 text-[11px] font-medium ${tones[managerStatusTone(status)]}`}>{managerStatusLabel(status, locale)}</span>}
    </div>
    {loadError && !state && <p role="alert" className="mb-0 mt-4 text-sm text-red-700">{c.loadError}</p>}
    {state && <>
      <p className={`mb-0 mt-4 flex gap-2 text-sm leading-6 ${status === "needs_attention" ? "text-red-700" : "text-plumo-ink"}`}>{status === "needs_attention" && <PlumoIcon icon={Alert02Icon} size={18} />}{managerExplanation(state, locale)}</p>
      {!state.service_bot_configured && <p className="mb-0 mt-3 inline-flex rounded-md bg-amber-50 px-2.5 py-1 text-xs text-amber-800">{c.noBot}</p>}
      {(state.recipient || state.candidate) && <dl className="mb-0 mt-4 space-y-2 rounded-xl bg-plumo-line/20 p-3 text-sm">
        {state.recipient && <div className="flex flex-wrap justify-between gap-2"><dt className="text-plumo-muted">{c.recipient}</dt><dd className="m-0 font-medium">{state.recipient.label}{state.recipient.at && <span className="font-normal text-plumo-muted"> · {formatTime(state.recipient.at, locale)}</span>}</dd></div>}
        {state.candidate && <div className="flex flex-wrap justify-between gap-2"><dt className="text-plumo-muted">{c.candidate}</dt><dd className="m-0 font-medium">{state.candidate.label}{state.candidate.at && <span className="font-normal text-plumo-muted"> · {formatTime(state.candidate.at, locale)}</span>}</dd></div>}
      </dl>}
      {isChangingManager(state) && <p className="mb-0 mt-2 text-xs leading-5 text-plumo-muted">{c.changing}</p>}
      {link && status === "waiting_code" && <div className="mt-4 rounded-xl bg-plumo-soft/70 p-4 text-[13px] leading-6">
        {link.link && <a href={link.link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium text-plumo-blue underline">{c.openBot}<PlumoIcon icon={LinkSquare02Icon} size={14} /></a>}
        <p className="mb-0 mt-2">{c.linkHint}</p>
        <code className="mt-1 block break-all rounded-md bg-white px-2 py-1 text-xs text-plumo-ink">{link.command}</code>
        {link.code_expires_at && <p className="mb-0 mt-2 text-xs text-plumo-muted">{c.expires} {formatTime(link.code_expires_at, locale)}</p>}
      </div>}
      {notice && <p role="status" className={`mb-0 mt-4 rounded-xl p-3 text-sm leading-6 ${notice.tone === "ok" ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800"}`}>{notice.text}</p>}
      <div className="mt-5 flex flex-wrap gap-2">
        {state.candidate && <button type="button" className={primary} disabled={busy !== null} onClick={confirm}>{spinner("confirm")}{c.confirm}</button>}
        <button type="button" className={state.recipient || state.candidate ? secondary : primary} disabled={busy !== null || !state.service_bot_configured} onClick={issue}>
          {spinner("link")}{status === "waiting_code" ? c.freshLink : state.recipient ? c.anotherLink : c.newLink}
        </button>
        {status !== "not_configured" && (confirming ? <div className="flex w-full flex-wrap items-center gap-2 rounded-lg bg-red-50 p-3 text-xs text-red-800" role="group"><span className="w-full">{c.confirmDisconnect}</span>
          <button type="button" className={`${secondary} border-red-300 text-red-700`} disabled={busy !== null} onClick={disconnect}>{spinner("disconnect")}{c.yes}</button>
          <button type="button" className={secondary} onClick={() => setConfirming(false)}>{c.no}</button></div>
          : <button type="button" className={`${secondary} text-red-700`} disabled={busy !== null} onClick={() => setConfirming(true)}>{c.disconnect}</button>)}
      </div>
    </>}
  </section>;
}
