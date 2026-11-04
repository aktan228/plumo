"use client";

import { useCallback, useState } from "react";
import { api, ApiError, goToLogin } from "@/lib/api/client";
import { usePolling } from "@/lib/api/use-polling";
import { useLanguage } from "@/lib/i18n";
import { formatTime } from "./dialogue-model";
import { conversationHref } from "./navigation";

type Recipient = { chat_id: string; name: string };
type Notification = { handoff_id: string; conversation_id: string; state: string; error: string | null; updated_at: string };
type Overview = { version: number; configured: boolean; state: string; recipient: Recipient | null; candidate: Recipient | null; expires_at: string | null; notifications: Notification[]; link?: string };
const button = "inline-flex min-h-10 cursor-pointer items-center justify-center rounded-lg border border-solid border-plumo-line bg-white px-4 py-2 text-sm text-plumo-ink hover:bg-plumo-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-default disabled:opacity-50";

export function ManagerRecipient() {
  const { locale } = useLanguage();
  const ru = locale === "ru";
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState<{ value: string; version: number } | null>(null);
  const [confirm, setConfirm] = useState<{ action: string; id?: string } | null>(null);
  const c = ru ? {
    title: "Уведомления менеджеру", intro: "Отдельный служебный бот сообщает о передаче клиентского диалога человеку. Подключите один личный чат менеджера для этого бизнеса.", loading: "Загружаем…", refresh: "Обновить", setup: "Служебный бот ещё не готов. Обратитесь к команде пилота для настройки.", connect: "Получить ссылку подключения", change: "Сменить получателя", disconnect: "Отключить", cancel: "Отмена", open: "Открыть служебного бота", step: "Откройте ссылку в Telegram и нажмите «Запустить». Вернитесь сюда, дождитесь найденного получателя и подтвердите его. Ссылка действует 10 минут и используется один раз.", expires: "Срок ссылки", active: "Текущий получатель", candidate: "Найден получатель — проверьте аккаунт", approve: "Подтвердить получателя", keep: "Текущий получатель продолжает получать уведомления до подтверждения нового.", confirm: "Подтвердите действие", revoke: "Новые уведомления перестанут отправляться этому менеджеру. Диалоги сохранятся в кабинете. Отправку, уже начатую служебным ботом, остановить нельзя.", retryWarning: "Проверьте в Telegram, пришло ли уведомление. Повтор может создать дубль. После подтверждения очередь отправит уведомление текущему подтверждённому менеджеру.", yes: "Подтверждаю", history: "Последние уведомления", empty: "Передач менеджеру ещё не было.", unknown: "Результат неизвестен. Проверьте чат менеджера перед повтором.", sent: "Telegram принял", failed: "Не отправлено", retry: "Повторить отправку", markSent: "Получение подтверждено", markFailed: "Не дошло", dialog: "Открыть диалог", failure: "Не удалось подтвердить результат действия. Обновите состояние перед повтором.", conflict: "Настройка изменилась. Обновите состояние перед подтверждением.", cooldown: "Подождите 30 секунд перед созданием новой ссылки.", expired: "Ссылка истекла или получатель ещё не найден. Создайте новую ссылку.", noRecipient: "Внешние уведомления не настроены. Обращения доступны в диалогах.",
  } : {
    title: "Manager notifications", intro: "A separate service bot notifies a manager when a customer conversation needs a person. Connect one private manager chat for this business.", loading: "Loading…", refresh: "Refresh", setup: "The service bot is not ready. Contact the pilot team to configure it.", connect: "Get connection link", change: "Change recipient", disconnect: "Disconnect", cancel: "Cancel", open: "Open service bot", step: "Open the link in Telegram and press Start. Return here, wait for the detected recipient and confirm the account. The link expires in 10 minutes and works once.", expires: "Link expiry", active: "Current recipient", candidate: "Recipient detected — check the account", approve: "Confirm recipient", keep: "The current recipient keeps receiving notifications until a new one is confirmed.", confirm: "Confirm action", revoke: "New notifications will no longer be sent to this manager. Conversations remain in the dashboard. A send already started by the service bot cannot be stopped.", retryWarning: "Check Telegram for the notification first. A retry may create a duplicate. After confirmation, the queue will send to the currently confirmed manager.", yes: "Confirm", history: "Recent notifications", empty: "No manager handoffs yet.", unknown: "Outcome unknown. Check the manager chat before retrying.", sent: "Accepted by Telegram", failed: "Not sent", retry: "Retry sending", markSent: "Receipt confirmed", markFailed: "Did not arrive", dialog: "Open conversation", failure: "Could not confirm the action result. Refresh the state before retrying.", conflict: "The setting changed. Refresh before confirming.", cooldown: "Wait 30 seconds before creating another link.", expired: "The link expired or no recipient was detected. Create a new link.", noRecipient: "External notifications are not configured. Enquiries are available in Conversations.",
  };
  const states: Record<string, string> = ru ? { demo: "Демонстрация · внешней доставки нет", not_configured: "Не настроено", awaiting_confirmation: "Ожидает подтверждения", ready: "Готово", attention: "Требует внимания", queued: "В очереди", retryable: "Ожидает повтора", running: "Отправляется", sending: "Отправляется", done: "Обработано", sent: c.sent, failed: c.failed, unknown: "Результат неизвестен" } : { demo: "Demo · no external delivery", not_configured: "Not configured", awaiting_confirmation: "Awaiting confirmation", ready: "Ready", attention: "Needs attention", queued: "Queued", retryable: "Waiting for retry", running: "Sending", sending: "Sending", done: "Processed", sent: c.sent, failed: c.failed, unknown: "Outcome unknown" };
  const reasons: Record<string, string> = ru ? {
    notify_recipient_missing: "Нет подтверждённого получателя.", notify_rejected: "Telegram отклонил отправку. Проверьте доступность служебного бота у менеджера и обратитесь к команде пилота.", retries_exhausted: "Попытки отправки исчерпаны.", business_mismatch: "Отправка остановлена. Обратитесь к команде пилота.",
  } : {
    notify_recipient_missing: "No confirmed recipient.", notify_rejected: "Telegram refused the send. Check the manager's access to the service bot and contact the pilot team.", retries_exhausted: "Send attempts exhausted.", business_mismatch: "Sending stopped. Contact the pilot team.",
  };
  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const next = await api<Overview>("manager-recipient", { signal });
      setData(previous => !previous || next.version >= previous.version ? next : previous);
      setError(previous => previous === "load_failed" ? null : previous);
    } catch (e) {
      if (signal?.aborted) throw e;
      if (e instanceof ApiError && e.unauthenticated) goToLogin();
      setError("load_failed"); throw e;
    }
  }, []);
  const refresh = usePolling(load, 5000, "manager-recipient");

  async function action(kind: string, id?: string) {
    if (!data) return;
    setBusy(true); setError(null);
    try {
      if (id) await api(`manager-recipient/notifications/${id}/resolve`, { method: "POST", body: { action: kind } });
      else {
        const result = await api<Overview>(`manager-recipient/${kind}`, { method: "POST", body: { version: data.version } });
        setData(result);
        if (result.link) setLink({ value: result.link, version: result.version });
        else setLink(null);
      }
      setConfirm(null); await load();
    } catch (e) {
      if (e instanceof ApiError && e.unauthenticated) goToLogin();
      setError(e instanceof ApiError ? e.code : "network_error"); refresh();
    } finally { setBusy(false); }
  }
  const errorText = error === "version_conflict" ? c.conflict : error === "manager_link_cooldown" ? c.cooldown : error === "manager_binding_expired" ? c.expired : c.failure;
  const linkVisible = link && data && link.version === data.version && data.expires_at && !data.candidate;

  return <section className="mt-6 rounded-2xl border border-solid border-plumo-line bg-white p-5 sm:p-6">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="m-0 text-lg font-semibold">{c.title}</h2><button type="button" className={button} disabled={busy} onClick={() => { setError(null); refresh(); }}>{c.refresh}</button></div>
    <p className="mb-4 mt-2 text-sm leading-6 text-plumo-muted">{c.intro}</p>
    {error && <p role="alert" className="rounded-lg bg-plumo-soft p-3 text-sm">{errorText}</p>}
    {!data ? <p role="status" className="text-sm">{c.loading}</p> : <>
      <p role="status" className="text-sm font-medium">{states[data.state] ?? c.failure}</p>
      {!data.configured && <p className="text-sm leading-6 text-plumo-muted">{c.setup}</p>}
      {data.recipient ? <p className="text-sm">{c.active}: <strong>{data.recipient.name}</strong> · {data.recipient.chat_id}</p> : <p className="text-sm leading-6 text-plumo-muted">{c.noRecipient}</p>}
      {data.state === "awaiting_confirmation" && <div className="my-4 rounded-xl bg-plumo-soft p-4 text-sm leading-6"><p className="m-0">{c.step}</p>{data.recipient && <p className="mb-0 mt-2">{c.keep}</p>}{linkVisible && <a href={link.value} target="_blank" rel="noreferrer" className="mt-3 inline-flex min-h-10 items-center text-plumo-blue underline">{c.open}</a>}<p className="mb-0 mt-2">{c.expires}: {formatTime(data.expires_at!, locale)}</p>{data.candidate && <div className="mt-3"><p className="m-0">{c.candidate}: <strong>{data.candidate.name}</strong> · {data.candidate.chat_id}</p><button type="button" className={`${button} mt-3`} disabled={busy || !data.configured} onClick={() => void action("confirm")}>{c.approve}</button></div>}<button type="button" className={`${button} mt-3`} disabled={busy} onClick={() => void action("cancel")}>{c.cancel}</button></div>}
      <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={busy || !data.configured} onClick={() => void action("link")}>{data.recipient ? c.change : c.connect}</button>{data.recipient && <button type="button" className={button} disabled={busy} onClick={() => setConfirm({ action: "disconnect" })}>{c.disconnect}</button>}</div>
      {confirm && <div role="group" aria-label={c.confirm} className="my-4 rounded-xl border border-solid border-plumo-line bg-plumo-soft p-4 text-sm leading-6"><p className="m-0">{confirm.action === "disconnect" ? c.revoke : c.retryWarning}</p><div className="mt-3 flex gap-2"><button type="button" className={button} disabled={busy} onClick={() => void action(confirm.action, confirm.id)}>{c.yes}</button><button type="button" className={button} disabled={busy} onClick={() => setConfirm(null)}>{c.cancel}</button></div></div>}
      <h3 className="mb-3 mt-6 text-sm font-semibold">{c.history}</h3>
      {data.notifications.length === 0 ? <p className="text-sm text-plumo-muted">{c.empty}</p> : <ul className="m-0 grid list-none gap-3 p-0">{data.notifications.map(item => <li key={item.handoff_id} className="rounded-lg border border-solid border-plumo-line p-3 text-sm"><div className="flex flex-wrap items-center gap-3"><span>{item.error === "confirmed_by_operator" ? c.markSent : states[item.state] ?? c.failure}</span><span className="text-xs text-plumo-muted">{formatTime(item.updated_at, locale)}</span><a href={conversationHref(item.conversation_id)} className="text-plumo-blue underline">{c.dialog}</a></div>{item.error && reasons[item.error] && <p className="mb-0 mt-2 text-sm text-plumo-muted">{reasons[item.error]}</p>}{item.state === "unknown" && <p className="mb-0 mt-2 text-sm">{c.unknown}</p>}{["failed", "unknown"].includes(item.state) && <div className="mt-3 flex flex-wrap gap-2">{item.state === "unknown" && <><button type="button" className={button} disabled={busy} onClick={() => void action("mark_sent", item.handoff_id)}>{c.markSent}</button><button type="button" className={button} disabled={busy} onClick={() => void action("mark_failed", item.handoff_id)}>{c.markFailed}</button></>}<button type="button" className={button} disabled={busy || !data.recipient || !data.configured} onClick={() => setConfirm({ action: "retry", id: item.handoff_id })}>{c.retry}</button></div>}</li>)}</ul>}
    </>}
  </section>;
}
