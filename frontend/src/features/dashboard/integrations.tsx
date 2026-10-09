"use client";

import { useRef, useState } from "react";
import Image from "next/image";
import { useLanguage } from "@/lib/i18n";
import { DashboardIcon } from "./dashboard-icon";
import { initialSetup, methods, setupStatus, validSetup, type IntegrationChannel, type ChannelSetup } from "./integration-model";
import { WhatsAppSetup } from "./whatsapp-setup";
import { initialWhatsAppDraft } from "./whatsapp-setup-model";

const channels: IntegrationChannel[] = ["WhatsApp", "Telegram", "Instagram"];
const copy = {
  ru: {
    title: "Интеграции", description: "Подключите каналы, в которых вам пишут клиенты.",
    none: "Не подключён", action: "Требуется действие", connect: "Подключить", connected: "Подключена", continue: "Продолжить настройку",
    whatsapp: "Входящие обращения на номер вашего бизнеса.", telegram: "Обращения клиентов через Telegram-бота.", instagram: "Сообщения клиентов в Instagram Direct.",
    off: "Ответы агента выключены", back: "К интеграциям", next: "Далее", previous: "Назад", save: "Сохранить настройки",
    steps: ["Способ подключения", "Подготовка", "Следующий шаг"],
    choose: "Как будем подключать", chooseText: "Выберите подходящий вариант. Сотрудник проверит возможность подключения для вашего аккаунта.",
    "business-app": "WhatsApp Business на телефоне", "business-appText": "Уже используете приложение для общения с клиентами. Обсудим подключение существующего номера.",
    cloud: "Отдельный номер для API", cloudText: "Планируете выделить номер для работы через Plumo. Условия подключения согласуем отдельно.",
    bot: "Telegram-бот", botText: "Клиенты будут писать боту вашего бизнеса. Личный аккаунт здесь не подключается.",
    business: "Бизнес-аккаунт", businessText: "Используете Instagram для компании или магазина.",
    creator: "Аккаунт автора", creatorText: "Принимаете обращения через профессиональный аккаунт автора.",
    prepare: "Подготовьте доступ к каналу", prepareText: "Проверьте два пункта перед согласованием подключения.",
    access: "У меня есть доступ к аккаунту или номеру бизнеса", manager: "Я могу согласовать подключение от имени бизнеса",
    checklist: "Что понадобится", waItems: ["Доступ к номеру бизнеса", "Информация о текущем приложении и аккаунте", "Сотрудник бизнеса для согласования"],
    tgItems: ["Доступ к управлению ботом", "Согласованный сценарий ответов", "Сотрудник бизнеса для согласования"],
    igItems: ["Доступ к профессиональному аккаунту", "Возможность управлять подключениями", "Сотрудник бизнеса для согласования"],
    security: "Пароли, коды подтверждения и токены в этой форме не нужны.",
    review: "Проверьте параметры", reviewText: "Сохраним выбранный вариант. Затем согласуйте подключение с сотрудником Plumo.",
    channel: "Канал", method: "Вариант", status: "Состояние", saved: "Настройки сохранены", savedText: "Канал ещё не подключён. Отправьте письмо сотруднику, чтобы согласовать следующий шаг.",
    email: "Подготовить письмо", emailHint: "Отправку выполняете вы в почтовом приложении.", edit: "Изменить настройки", dialogues: "Открыть диалоги",
    helpTitle: "Подключение и запуск — два шага", helpText: "Сначала подключаем канал и проверяем сообщения. После проверки отдельно включаем ответы агента.",
    storage: "Настройки остаются в этой вкладке до перезагрузки.",
  },
  en: {
    title: "Integrations", description: "Connect the channels your customers use.",
    none: "Not connected", action: "Action required", connect: "Connect", connected: "Connected", continue: "Continue setup",
    whatsapp: "Incoming enquiries to your business number.", telegram: "Customer enquiries through a Telegram bot.", instagram: "Customer messages in Instagram Direct.",
    off: "Agent replies are off", back: "Back to integrations", next: "Next", previous: "Back", save: "Save settings",
    steps: ["Connection method", "Preparation", "Next step"],
    choose: "How would you like to connect", chooseText: "Choose an option. A team member will check whether it is available for your account.",
    "business-app": "WhatsApp Business on your phone", "business-appText": "You already use the app to talk to customers. We will discuss connecting your existing number.",
    cloud: "A separate number for the API", cloudText: "You plan to use a dedicated number with Plumo. Connection terms will be agreed separately.",
    bot: "Telegram bot", botText: "Customers will message your business bot. Personal accounts are not connected here.",
    business: "Business account", businessText: "You use Instagram for a company or shop.",
    creator: "Creator account", creatorText: "You receive enquiries through a professional creator account.",
    prepare: "Prepare access to the channel", prepareText: "Check these two items before agreeing the connection.",
    access: "I have access to the business account or number", manager: "I can authorize the connection for the business",
    checklist: "What you will need", waItems: ["Access to the business number", "Details of your current app and account", "A business representative to agree the connection"],
    tgItems: ["Access to manage the bot", "An agreed response scenario", "A business representative to agree the connection"],
    igItems: ["Access to a professional account", "Permission to manage connections", "A business representative to agree the connection"],
    security: "No passwords, verification codes or tokens are needed in this form.",
    review: "Review your settings", reviewText: "Save your selection, then agree the connection with a Plumo team member.",
    channel: "Channel", method: "Option", status: "Status", saved: "Settings saved", savedText: "The channel is not connected yet. Send an email to agree the next step with the team.",
    email: "Prepare email", emailHint: "You send the email from your email app.", edit: "Edit settings", dialogues: "Open conversations",
    helpTitle: "Connect first, then launch", helpText: "First connect the channel and check messages. Agent replies are enabled separately after testing.",
    storage: "Settings stay in this tab until you reload.",
  },
};
type MethodKey = "business-app" | "cloud" | "bot" | "business" | "creator";
const primary = "inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 rounded-lg border-0 bg-plumo-blue px-4 py-2.5 font-[inherit] text-sm font-medium text-white transition-colors hover:bg-plumo-blue/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-not-allowed disabled:bg-plumo-line disabled:text-plumo-muted";
const secondary = "inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 rounded-lg border border-solid border-plumo-line bg-white px-4 py-2.5 font-[inherit] text-sm text-plumo-ink hover:bg-plumo-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue";
const channelLogos = { WhatsApp: "/images/channels/whatsapp-business.png", Telegram: "/images/channels/telegram.svg", Instagram: "/images/channels/instagram.svg" };
const channelLabel = (channel: IntegrationChannel) => channel === "WhatsApp" ? "WhatsApp Business" : channel;

function ChannelIcon({ channel }: { channel: IntegrationChannel }) {
  return <Image src={channelLogos[channel]} alt={channelLabel(channel)} width={48} height={48} className="size-12 shrink-0 object-contain" />;
}

export function Integrations({ onDialogues, connectedChannels = [] }: { onDialogues: () => void; connectedChannels?: readonly IntegrationChannel[] }) {
  const { locale } = useLanguage();
  const c = copy[locale];
  const [saved, setSaved] = useState<Partial<Record<IntegrationChannel, ChannelSetup>>>({});
  const [active, setActive] = useState<IntegrationChannel | null>(null);
  const [setup, setSetup] = useState<ChannelSetup>(initialSetup("WhatsApp"));
  const [step, setStep] = useState(0);
  const [complete, setComplete] = useState(false);
  const [whatsappDraft, setWhatsappDraft] = useState(initialWhatsAppDraft);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const containerRef = useRef<HTMLElement>(null);
  const focusTitle = () => requestAnimationFrame(() => {
    if (containerRef.current) containerRef.current.scrollTop = 0;
    titleRef.current?.focus({ preventScroll: true });
  });
  const descriptions = { WhatsApp: c.whatsapp, Telegram: c.telegram, Instagram: c.instagram };
  function open(channel: IntegrationChannel) {
    if (connectedChannels.includes(channel)) return;
    setActive(channel); setSetup(saved[channel] ?? initialSetup(channel)); setStep(0); setComplete(false); focusTitle();
  }
  function close() { setActive(null); setComplete(false); focusTitle(); }
  function advance() { setStep(value => value + 1); focusTitle(); }
  function finish() {
    if (!active || !validSetup(active, setup)) return;
    setSaved(values => ({ ...values, [active]: { ...setup } })); setComplete(true); focusTitle();
  }
  const requirementItems = active === "WhatsApp" ? c.waItems : active === "Telegram" ? c.tgItems : c.igItems;
  const methodLabel = c[setup.method as MethodKey];
  const emailBody = `${locale === "ru" ? "Здравствуйте! Хочу согласовать подключение канала к Plumo." : "Hello! I would like to discuss connecting a channel to Plumo."}\n\n${c.channel}: ${active ? channelLabel(active) : ""}\n${c.method}: ${methodLabel}`;

  return <section ref={containerRef} className="h-full overflow-y-auto bg-plumo-line/15 px-5 py-6 sm:px-8 sm:py-8">
    <div className="mx-auto max-w-[1120px]">
      {!active ? <>
        <h1 ref={titleRef} tabIndex={-1} className="m-0 text-2xl font-semibold tracking-tight outline-none">{c.title}</h1>
        <p className="mb-0 mt-2 text-sm leading-6 text-plumo-muted">{c.description}</p>
        <div className="mt-6 grid gap-4 lg:grid-cols-3">{channels.map(channel => {
          const connected = setupStatus(saved[channel], connectedChannels.includes(channel)) === "connected";
          const buttonLabel = connected ? c.connected : saved[channel] ? c.continue : c.connect;
          return <article key={channel} className="flex flex-col rounded-2xl border border-solid border-plumo-line bg-white p-6">
          <ChannelIcon channel={channel} />
          <h2 className="mb-0 mt-5 text-lg font-semibold">{channelLabel(channel)}</h2><p className="mb-0 mt-2 flex-1 text-sm leading-6 text-plumo-muted">{descriptions[channel]}</p>
          <button type="button" disabled={connected} className={`mt-6 ${connected ? "inline-flex min-h-10 cursor-default items-center justify-center gap-2 rounded-lg border-0 bg-plumo-line px-4 py-2.5 font-[inherit] text-sm font-medium text-plumo-muted" : saved[channel] ? secondary : primary}`} onClick={() => open(channel)} aria-label={`${buttonLabel} ${channelLabel(channel)}`}>{connected && <DashboardIcon name="check" size={16} />}{buttonLabel}</button>
        </article>;
        })}</div>
        <div className="mt-8 flex flex-wrap items-center justify-between gap-5 rounded-2xl border border-solid border-plumo-line bg-white p-6"><div className="max-w-[650px]"><h2 className="m-0 text-sm font-medium">{c.helpTitle}</h2><p className="mb-0 mt-2 text-sm leading-6 text-plumo-muted">{c.helpText}</p></div><button type="button" className={secondary} onClick={onDialogues}><DashboardIcon name="chat" size={17} />{c.dialogues}</button></div>
      </> : active === "WhatsApp" ? <WhatsAppSetup draft={whatsappDraft} onChange={setWhatsappDraft} onBack={close} onSave={() => setSaved(values => ({ ...values, WhatsApp: { ...initialSetup("WhatsApp"), method: whatsappDraft.method } }))} /> : <>
        <button type="button" className={`${secondary} mb-6`} onClick={close}><DashboardIcon name="back" size={16} />{c.back}</button>
        <div className="overflow-hidden rounded-2xl border border-solid border-plumo-line bg-white">
          <div className="grid lg:grid-cols-[1.35fr_1fr]">
            <div className="p-6 sm:p-9">
              <div className="mb-7 flex flex-wrap items-center justify-between gap-4"><ChannelIcon channel={active} /><span className="text-xs text-plumo-muted">{channelLabel(active)}</span></div>
              {!complete && <ol aria-label={locale === "ru" ? "Этапы подключения" : "Connection steps"} className="mb-7 mt-0 flex list-none gap-2 p-0">{c.steps.map((label, index) => <li key={label} aria-current={index === step ? "step" : undefined} title={label} className={`h-1.5 flex-1 rounded-full ${index <= step ? "bg-plumo-blue" : "bg-plumo-line"}`}><span className="sr-only">{index + 1}. {label}</span></li>)}</ol>}
              <h1 ref={titleRef} tabIndex={-1} className="m-0 text-2xl font-medium leading-tight tracking-tight outline-none">{complete ? c.saved : step === 0 ? `${c.choose} ${channelLabel(active)}?` : step === 1 ? c.prepare : c.review}</h1>
              <p className="mb-6 mt-3 text-sm leading-6 text-plumo-muted">{complete ? c.savedText : step === 0 ? c.chooseText : step === 1 ? c.prepareText : c.reviewText}</p>
              {!complete && step === 0 && <fieldset className="m-0 space-y-3 border-0 p-0"><legend className="sr-only">{c.method}</legend>{methods[active].map(value => <label key={value} className={`flex cursor-pointer items-start gap-3 rounded-xl border border-solid p-4 transition-colors ${setup.method === value ? "border-plumo-blue bg-plumo-soft/50" : "border-plumo-line hover:bg-plumo-line/20"}`}><input type="radio" name="connection-method" value={value} checked={setup.method === value} onChange={() => setSetup(current => ({ ...current, method: value }))} className="mt-1 shrink-0 accent-plumo-blue" /><span><span className="block text-sm font-medium">{c[value as MethodKey]}</span><span className="mt-1.5 block text-xs leading-6 text-plumo-muted">{c[`${value}Text` as "business-appText" | "cloudText" | "botText" | "businessText" | "creatorText"]}</span></span></label>)}</fieldset>}
              {!complete && step === 1 && <div className="space-y-3">{(["access", "manager"] as const).map(key => <label key={key} className="flex cursor-pointer items-start gap-3 rounded-xl border border-solid border-plumo-line p-4"><input type="checkbox" checked={setup[key]} onChange={event => setSetup(current => ({ ...current, [key]: event.target.checked }))} className="mt-0.5 accent-plumo-blue" /><span className="text-sm leading-6">{c[key]}</span></label>)}<p className="m-0 pt-2 text-xs leading-6 text-plumo-muted">{c.security}</p></div>}
              {(complete || step === 2) && <dl className="m-0 space-y-4 rounded-xl bg-plumo-line/20 p-5">{[[c.channel, channelLabel(active)], [c.method, methodLabel], [c.status, complete ? c.action : c.none]].map(([label, value]) => <div key={label} className="flex flex-wrap justify-between gap-2"><dt className="text-xs text-plumo-muted">{label}</dt><dd className="m-0 text-right text-xs font-medium">{value}</dd></div>)}</dl>}
              <div className="mt-8 flex flex-wrap items-center gap-3">
                {complete ? <><a href={`mailto:contact@plumo.app?subject=${encodeURIComponent(`${locale === "ru" ? "Подключение" : "Connect"} ${active ? channelLabel(active) : ""} — Plumo`)}&body=${encodeURIComponent(emailBody)}`} className={primary}>{c.email}<DashboardIcon name="send" size={16} /></a><button type="button" className={secondary} onClick={() => { setComplete(false); setStep(0); focusTitle(); }}>{c.edit}</button></> : <>{step > 0 && <button type="button" className={secondary} onClick={() => { setStep(value => value - 1); focusTitle(); }}>{c.previous}</button>}<button type="button" className={`${primary} flex-1`} disabled={step > 0 && !validSetup(active, setup)} onClick={step === 2 ? finish : advance}>{step === 2 ? c.save : c.next}</button></>}
              </div>
              <p className="mb-0 mt-4 text-[11px] leading-5 text-plumo-muted">{complete ? c.emailHint : c.storage}</p>
            </div>
            <aside className="flex flex-col justify-center gap-5 border-0 border-t border-solid border-plumo-line bg-plumo-line/20 p-6 sm:p-9 lg:border-l lg:border-t-0">
              <div className="rounded-2xl border border-solid border-plumo-line bg-white p-5"><h2 className="m-0 text-sm font-medium">{c.checklist}</h2><ul className="mb-0 mt-4 list-none space-y-4 p-0">{requirementItems.map(item => <li key={item} className="flex items-start gap-2.5 text-xs leading-5"><span className="mt-0.5 shrink-0 text-plumo-blue"><DashboardIcon name="check" size={16} /></span>{item}</li>)}</ul></div>
              <div className="rounded-2xl bg-plumo-soft p-5"><h2 className="m-0 text-sm font-medium">{c.helpTitle}</h2><p className="mb-0 mt-2 text-xs leading-6 text-plumo-muted">{c.helpText}</p><p className="mb-0 mt-3 text-xs font-medium text-plumo-blue">{c.off}</p></div>
            </aside>
          </div>
        </div>
      </>}
    </div>
  </section>;
}
