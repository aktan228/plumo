"use client";

import { useCallback, useRef, useState } from "react";
import Image from "next/image";
import Alert02Icon from "@hugeicons/core-free-icons/Alert02Icon";
import Chatting01Icon from "@hugeicons/core-free-icons/Chatting01Icon";
import LinkSquare02Icon from "@hugeicons/core-free-icons/LinkSquare02Icon";
import Loading03Icon from "@hugeicons/core-free-icons/Loading03Icon";
import Refresh01Icon from "@hugeicons/core-free-icons/Refresh01Icon";
import { PlumoIcon } from "@/components/ui/plumo-icon";
import { ApiError, api, goToLogin } from "@/lib/api/client";
import type { ChannelIntegration, Connection, IntegrationChannel, IntegrationsResponse } from "@/lib/api/types";
import { usePolling } from "@/lib/api/use-polling";
import { useLanguage } from "@/lib/i18n";
import { apiErrorText } from "./api-messages";
import { formatTime } from "./dialogue-model";
import { cardStatus, statusLabel, statusTone } from "./integration-model";
import { TelegramSetup } from "./telegram-setup";
import { ChannelSetup } from "./channel-setup";
import { WhatsAppSetup } from "./whatsapp-setup";
import { initialWhatsAppDraft } from "./whatsapp-setup-model";

const copy = {
  ru: {
    title: "Интеграции", description: "Подключите каналы, в которых вам пишут клиенты.",
    whatsapp: "Входящие обращения на номер вашего бизнеса.", telegram: "Обращения клиентов через Telegram-бота бизнеса.", instagram: "Сообщения клиентов в Instagram Direct.",
    connect: "Подключить", reconnect: "Подключить снова", continue: "Продолжить настройку", check: "Проверить", disconnect: "Отключить",
    confirmDisconnect: "Отключить канал? Приём и отправка остановятся, история сохранится.", yes: "Да, отключить", no: "Отмена",
    agentOn: "Ответы агента включены", agentOff: "Ответы агента выключены", enable: "Включить агента", disable: "Выключить агента",
    lastCheck: "Проверено", lastEvent: "Последнее сообщение", never: "ещё не было", openBot: "Открыть бота", openProfile: "Открыть профиль",
    demo: "Демо: подключение согласуется с командой Plumo.",
    loading: "Загружаем интеграции…", loadError: "Не удалось загрузить интеграции.", retry: "Повторить",
    back: "К интеграциям", method: "Способ подключения",
    tgTitle: "Подключение Telegram-бота", igTitle: "Подключение Instagram",
    tgMethod: "Бот бизнеса создаётся в @BotFather, его токен команда размещает на сервере. Здесь выбирается подготовленная конфигурация — токен не вводится в браузере и не показывается.",
    igMethod: "Instagram API with Instagram Login, токен профессионального аккаунта подготовлен на сервере. Полный OAuth для самостоятельного подключения в этой версии не используется.",
    choose: "Серверная конфигурация", none: "Для этого бизнеса нет подготовленной конфигурации.",
    serverReady: "Настройки сервера", submit: "Проверить и подключить", submitting: "Проверяем…",
    replace: "Заменить webhook", conflictHint: "Если это старый адрес Plumo (например, прежний туннель), замените его. Чужую настройку не трогайте.",
    connectedOk: "Канал подключён. Напишите в него с другого аккаунта и проверьте «Диалоги». Ответы агента включаются отдельно, после проверки.",
    igNeeds: "Что нужно от владельца аккаунта Meta", callback: "Callback URL для Meta App Dashboard",
    igItems: [
      "Профессиональный аккаунт Instagram (Business или Creator)",
      "Meta app типа Business с продуктом Instagram API with Instagram Login",
      "Разрешения instagram_business_basic и instagram_business_manage_messages",
      "Приложение в режиме Live; тестовые аккаунты с ролью в приложении",
      "Webhook подписан на поле messages, verify token совпадает с сервером",
    ],
    tgItems: ["Бот создан в @BotFather, токен на сервере", "Публичный HTTPS-адрес API для webhook", "Сначала тестовое сообщение, потом — включение агента"],
    help: "Подключение и запуск — два шага", helpText: "Сначала подключаем канал и проверяем входящие. После проверки отдельно включаем ответы агента.",
    dialogues: "Открыть диалоги", mock: "Модель: mock — ответы ядра без живой LLM.",
    requirement: { public_url: "Публичный HTTPS-адрес API (PUBLIC_BASE_URL)", secret_key: "CHANNEL_SECRET_KEY", credentials_file: "Файл серверных конфигураций", app_secret: "INSTAGRAM_APP_SECRET", verify_token: "INSTAGRAM_VERIFY_TOKEN" } as Record<string, string>,
  },
  en: {
    title: "Integrations", description: "Connect the channels your customers use.",
    whatsapp: "Incoming enquiries to your business number.", telegram: "Customer enquiries through the business's Telegram bot.", instagram: "Customer messages in Instagram Direct.",
    connect: "Connect", reconnect: "Connect again", continue: "Continue setup", check: "Check", disconnect: "Disconnect",
    confirmDisconnect: "Disconnect the channel? Receiving and sending stop; history is kept.", yes: "Yes, disconnect", no: "Cancel",
    agentOn: "Agent replies are on", agentOff: "Agent replies are off", enable: "Turn agent on", disable: "Turn agent off",
    lastCheck: "Checked", lastEvent: "Last message", never: "none yet", openBot: "Open bot", openProfile: "Open profile",
    demo: "Demo: the connection is agreed with the Plumo team.",
    loading: "Loading integrations…", loadError: "Could not load integrations.", retry: "Retry",
    back: "Back to integrations", method: "Connection method",
    tgTitle: "Connect a Telegram bot", igTitle: "Connect Instagram",
    tgMethod: "The business bot is created in @BotFather and its token is placed on the server by the team. Here you pick the prepared configuration; the token is never typed or shown in the browser.",
    igMethod: "Instagram API with Instagram Login; the professional account's token is prepared on the server. Full self-service OAuth is not used in this version.",
    choose: "Server configuration", none: "No configuration is prepared for this business.",
    serverReady: "Server settings", submit: "Check and connect", submitting: "Checking…",
    replace: "Replace webhook", conflictHint: "If this is an old Plumo address (e.g. a previous tunnel), replace it. Leave other systems' settings alone.",
    connectedOk: "Channel connected. Message it from another account and check Conversations. Agent replies are switched on separately, after testing.",
    igNeeds: "What the Meta account owner must provide", callback: "Callback URL for the Meta App Dashboard",
    igItems: [
      "A professional Instagram account (Business or Creator)",
      "A Business-type Meta app with Instagram API with Instagram Login",
      "Permissions instagram_business_basic and instagram_business_manage_messages",
      "The app in Live mode; test accounts with a role in the app",
      "Webhook subscribed to the messages field, verify token matching the server",
    ],
    tgItems: ["Bot created in @BotFather, token on the server", "A public HTTPS address of the API for the webhook", "A test message first, then switch the agent on"],
    help: "Connect first, then launch", helpText: "First connect the channel and check incoming messages. Agent replies are switched on separately after testing.",
    dialogues: "Open conversations", mock: "Model: mock — core replies without a live LLM.",
    requirement: { public_url: "Public HTTPS address of the API (PUBLIC_BASE_URL)", secret_key: "CHANNEL_SECRET_KEY", credentials_file: "Server configuration file", app_secret: "INSTAGRAM_APP_SECRET", verify_token: "INSTAGRAM_VERIFY_TOKEN" } as Record<string, string>,
  },
};

const primary = "inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 rounded-lg border-0 bg-plumo-blue px-4 py-2.5 font-[inherit] text-sm font-medium text-white transition-colors hover:bg-plumo-blue/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-not-allowed disabled:bg-plumo-line disabled:text-plumo-muted";
const secondary = "inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 rounded-lg border border-solid border-plumo-line bg-white px-4 py-2.5 font-[inherit] text-sm text-plumo-ink hover:bg-plumo-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-not-allowed disabled:opacity-60";
const logos = { whatsapp: "/images/channels/whatsapp-business.png", telegram: "/images/channels/telegram.svg", instagram: "/images/channels/instagram.svg" };
const names = { whatsapp: "WhatsApp Business", telegram: "Telegram", instagram: "Instagram" };
const tones = { ok: "bg-emerald-50 text-emerald-700", warn: "bg-amber-50 text-amber-700", error: "bg-red-50 text-red-700", idle: "bg-plumo-line/60 text-plumo-muted" };

type Active = "whatsapp" | IntegrationChannel | null;
type Notice = { channel: IntegrationChannel; tone: "ok" | "error"; text: string; conflict?: boolean } | null;

function Logo({ channel }: { channel: keyof typeof logos }) {
  return <Image src={logos[channel]} alt={names[channel]} width={48} height={48} className="size-12 shrink-0 object-contain" />;
}

export function Integrations({ onDialogues, onStateChange }: { onDialogues: () => void; onStateChange?: (data: IntegrationsResponse) => void }) {
  const { locale } = useLanguage();
  const c = copy[locale];
  const [data, setData] = useState<IntegrationsResponse | null>(null);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [active, setActive] = useState<Active>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [whatsappDraft, setWhatsappDraft] = useState(initialWhatsAppDraft);
  const [whatsappSaved, setWhatsappSaved] = useState(false);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const containerRef = useRef<HTMLElement>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const result = await api<IntegrationsResponse>("integrations", { signal });
      setData(result);
      onStateChange?.(result);
      setLoadError(null);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.unauthenticated) goToLogin();
        setLoadError(error);
      }
      throw error;
    }
  }, [onStateChange]);
  // Statuses also change on the server (a revoked token found by the worker): refresh now and then.
  const refresh = usePolling(load, 15_000, "integrations");

  function focusTitle() {
    requestAnimationFrame(() => {
      if (containerRef.current) containerRef.current.scrollTop = 0;
      titleRef.current?.focus({ preventScroll: true });
    });
  }
  function open(channel: Active) { setActive(channel); setNotice(null); focusTitle(); }
  function close() { setActive(null); focusTitle(); }

  async function run(key: string, channel: IntegrationChannel, action: () => Promise<unknown>, success?: string) {
    setBusy(key);
    setNotice(null);
    try {
      await action();
      if (success) setNotice({ channel, tone: "ok", text: success });
      return true;
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.unauthenticated) goToLogin();
        setNotice({ channel, tone: "error", text: apiErrorText(error.code, locale, error.message), conflict: error.code === "webhook_conflict" });
      }
      return false;
    } finally {
      setBusy(null);
      refresh();
    }
  }

  async function connect(item: ChannelIntegration, replaceWebhook = false, chosenRef?: string) {
    const ref = chosenRef ?? item.credentials[0]?.ref;
    if (!ref) return;
    const done = await run(`connect:${item.channel}`, item.channel, () => api<Connection>(`integrations/${item.channel}/connect`, { method: "POST", body: { credential_ref: ref, replace_webhook: replaceWebhook } }), c.connectedOk);
    if (done) { setActive(null); focusTitle(); }
  }

  async function connectTelegram(token: string, replace: boolean) {
    const done = await run("connect:telegram", "telegram", () => api("integrations/telegram/connect", { method: "POST", body: { token, replace_webhook: replace } }), c.connectedOk);
    if (done) { setActive(null); focusTitle(); }
    return done;
  }

  const channels = data?.channels ?? [];
  const selected = channels.find(item => item.channel === active);

  return <section ref={containerRef} className="h-full overflow-y-auto bg-plumo-line/15 px-5 py-6 sm:px-8 sm:py-8">
    <div className="mx-auto max-w-[1120px]">
      {active === "whatsapp" ? <WhatsAppSetup draft={whatsappDraft} onChange={setWhatsappDraft} onBack={close} onSave={() => setWhatsappSaved(true)} />
        : selected?.channel === "telegram" ? <TelegramSetup item={selected} busy={busy === "connect:telegram"} notice={notice?.channel === "telegram" ? notice : null} onBack={close} onConnect={connectTelegram} />
        : selected ? <ChannelSetup key={selected.channel} item={selected} busy={busy === `connect:${selected.channel}`} notice={notice?.channel === selected.channel ? notice : null} onBack={close} onConnect={(ref, replace) => connect(selected, replace, ref)} />
        : <>
          <h1 ref={titleRef} tabIndex={-1} className="m-0 text-2xl font-semibold tracking-tight outline-none">{c.title}</h1>
          <p className="mb-0 mt-2 text-sm leading-6 text-plumo-muted">{c.description}</p>
          {data?.ai_mode === "mock" && <p className="mb-0 mt-3 inline-flex rounded-md bg-amber-50 px-2.5 py-1 text-xs text-amber-800">{c.mock}</p>}
          {!data && !loadError && <p role="status" className="mt-8 flex items-center gap-2 text-sm text-plumo-muted"><PlumoIcon icon={Loading03Icon} size={18} className="animate-spin" />{c.loading}</p>}
          {loadError && <div role="alert" className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-solid border-red-200 bg-red-50 p-4 text-sm text-red-800"><span>{c.loadError} {apiErrorText(loadError.code, locale)}</span><button type="button" className={secondary} onClick={refresh}><PlumoIcon icon={Refresh01Icon} size={16} />{c.retry}</button></div>}
          {notice && !active && <p role="status" className={`mt-6 rounded-xl p-4 text-sm leading-6 ${notice.tone === "ok" ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800"}`}>{notice.text}</p>}
          <div className="mt-6 grid gap-4 lg:grid-cols-3">
            <article className="flex flex-col rounded-2xl border border-solid border-plumo-line bg-white p-6">
              <Logo channel="whatsapp" />
              <h2 className="mb-0 mt-5 text-lg font-semibold">{names.whatsapp}</h2>
              <p className="mb-0 mt-2 flex-1 text-sm leading-6 text-plumo-muted">{c.whatsapp}</p>
              <p className="mb-0 mt-3 text-xs leading-5 text-plumo-muted">{c.demo}</p>
              <button type="button" className={`mt-6 ${whatsappSaved ? secondary : primary}`} onClick={() => open("whatsapp")} aria-label={`${whatsappSaved ? c.continue : c.connect} ${names.whatsapp}`}>{whatsappSaved ? c.continue : c.connect}</button>
            </article>
            {channels.map(item => renderCard(item))}
          </div>
          <div className="mt-8 flex flex-wrap items-center justify-between gap-5 rounded-2xl border border-solid border-plumo-line bg-white p-6"><div className="max-w-[650px]"><h2 className="m-0 text-sm font-medium">{c.help}</h2><p className="mb-0 mt-2 text-sm leading-6 text-plumo-muted">{c.helpText}</p></div><button type="button" className={secondary} onClick={onDialogues}><PlumoIcon icon={Chatting01Icon} size={17} />{c.dialogues}</button></div>
        </>}
    </div>
  </section>;

  function renderCard(item: ChannelIntegration) {
    const status = cardStatus(item);
    const connection = item.connection && item.connection.status !== "disconnected" ? item.connection : null;
    const description = item.channel === "telegram" ? c.telegram : c.instagram;
    const cardNotice = notice && notice.channel === item.channel ? notice : null;
    return <article key={item.channel} className="flex flex-col rounded-2xl border border-solid border-plumo-line bg-white p-6">
      <div className="flex items-start justify-between gap-3"><Logo channel={item.channel} /><span className={`rounded-md px-2 py-1 text-[11px] font-medium ${tones[statusTone(status)]}`}>{statusLabel(status, locale)}</span></div>
      <h2 className="mb-0 mt-5 text-lg font-semibold">{names[item.channel]}</h2>
      <p className="mb-0 mt-2 text-sm leading-6 text-plumo-muted">{description}</p>
      {connection && <dl className="mb-0 mt-4 space-y-2 rounded-xl bg-plumo-line/20 p-3 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2"><dt className="sr-only">Account</dt><dd className="m-0 font-medium">{connection.account.display_name}{connection.account.username && <span className="font-normal text-plumo-muted"> · @{connection.account.username}</span>}</dd>{connection.account.link && <a href={connection.account.link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-plumo-blue hover:underline">{item.channel === "telegram" ? c.openBot : c.openProfile}<PlumoIcon icon={LinkSquare02Icon} size={14} /></a>}</div>
        <div className="flex justify-between gap-2"><dt className="text-plumo-muted">{c.lastCheck}</dt><dd className="m-0">{connection.last_check_at ? formatTime(connection.last_check_at, locale) : "—"}</dd></div>
        <div className="flex justify-between gap-2"><dt className="text-plumo-muted">{c.lastEvent}</dt><dd className="m-0">{connection.last_event_at ? formatTime(connection.last_event_at, locale) : c.never}</dd></div>
        <div className={`font-medium ${connection.agent_enabled ? "text-emerald-700" : "text-plumo-blue"}`}>{connection.agent_enabled ? c.agentOn : c.agentOff}</div>
      </dl>}
      {(connection?.last_error || (!connection && item.connection?.last_error && status !== "not_connected")) && <p className="mb-0 mt-3 flex gap-2 text-xs leading-5 text-red-700"><PlumoIcon icon={Alert02Icon} size={16} />{(connection ?? item.connection)!.last_error!.message}</p>}
      {cardNotice && <p role="status" className={`mb-0 mt-3 text-xs leading-5 ${cardNotice.tone === "ok" ? "text-emerald-700" : "text-red-700"}`}>{cardNotice.text}</p>}
      {connection?.channel === "telegram" && connection.verification && <div className="mt-4 rounded-xl bg-plumo-soft/70 p-4 text-[13px] leading-6">
        <p className="m-0 font-medium">{locale === "ru" ? "Проверка подключения" : "Connection verification"}</p>
        <p className="mb-0 mt-2">{connection.verification.state === "verified" ? (locale === "ru" ? "Контрольное сообщение принято Telegram. Можно включить ответы агента." : "Telegram accepted the control message. You can enable agent replies.") : (locale === "ru" ? "Откройте бота по ссылке, нажмите «Запустить» и дождитесь контрольного сообщения. Затем обновите проверку." : "Open the bot link, press Start and wait for the control message. Then refresh the check.")}</p>
        {connection.status === "connected" && connection.verification.link && <a href={connection.verification.link} target="_blank" rel="noreferrer" className="mt-3 inline-block text-plumo-blue underline">{locale === "ru" ? "Открыть бота для проверки" : "Open bot to verify"}</a>}
        {connection.verification.state === "sending" && <p role="status" className="mb-0 mt-2">{locale === "ru" ? "Отправляем контрольное сообщение…" : "Sending the control message…"}</p>}
        {["unknown", "failed", "expired", "required"].includes(connection.verification.state) && <><p className="mb-0 mt-2">{locale === "ru" ? "Проверка не завершена. Получите новую ссылку и повторите её." : "Verification is incomplete. Get a new link and retry."}</p><button type="button" disabled={busy !== null || connection.status !== "connected"} className={`${secondary} mt-3`} onClick={() => run(`verification:${connection.id}`, "telegram", () => api(`integrations/${connection.id}/verification`, { method: "POST" }))}>{locale === "ru" ? "Новая проверочная ссылка" : "New verification link"}</button></>}
      </div>}
      <div className="flex-1" />
      {connection ? <div className="mt-5 flex flex-wrap gap-2">
        <button type="button" className={secondary} disabled={busy !== null} onClick={() => run(`check:${connection.id}`, item.channel, () => api(`integrations/${connection.id}/check`, { method: "POST" }))}>{busy === `check:${connection.id}` ? <PlumoIcon icon={Loading03Icon} size={16} className="animate-spin" /> : <PlumoIcon icon={Refresh01Icon} size={16} />}{c.check}</button>
        <button type="button" className={connection.agent_enabled ? secondary : primary} disabled={busy !== null || (!connection.agent_enabled && connection.auth_method === "bot_token" && (connection.status !== "connected" || connection.verification?.state !== "verified"))} aria-pressed={connection.agent_enabled}
          onClick={() => run(`agent:${connection.id}`, item.channel, () => api(`integrations/${connection.id}`, { method: "PATCH", body: { agent_enabled: !connection.agent_enabled, version: connection.version } }))}>{busy === `agent:${connection.id}` && <PlumoIcon icon={Loading03Icon} size={16} className="animate-spin" />}{connection.agent_enabled ? c.disable : c.enable}</button>
        {(connection.status !== "connected" || connection.auth_method === "bot_token") && <button type="button" className={secondary} disabled={busy !== null} onClick={() => open(item.channel)}>{c.reconnect}</button>}
        {confirming === connection.id ? <div className="flex w-full flex-wrap items-center gap-2 rounded-lg bg-red-50 p-3 text-xs text-red-800" role="group"><span className="w-full">{c.confirmDisconnect}</span>
          <button type="button" className={`${secondary} border-red-300 text-red-700`} disabled={busy !== null} onClick={async () => { await run(`disconnect:${connection.id}`, item.channel, () => api(`integrations/${connection.id}/disconnect`, { method: "POST" })); setConfirming(null); }}>{c.yes}</button>
          <button type="button" className={secondary} onClick={() => setConfirming(null)}>{c.no}</button></div>
          : <button type="button" className={`${secondary} text-red-700`} disabled={busy !== null} onClick={() => setConfirming(connection.id)}>{c.disconnect}</button>}
      </div>
        : <button type="button" className={`mt-6 ${primary}`} onClick={() => open(item.channel)} aria-label={`${item.connection ? c.reconnect : c.connect} ${names[item.channel]}`}>{item.connection ? c.reconnect : c.connect}</button>}
    </article>;
  }
}
