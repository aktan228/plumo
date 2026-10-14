"use client";

import Image from "next/image";
import { useRef, useState, type ReactNode } from "react";
import { useLanguage } from "@/lib/i18n";
import { PlumoIcon } from "@/components/ui/plumo-icon";
import AiChat02Icon from "@hugeicons/core-free-icons/AiChat02Icon";
import ArrowLeft01Icon from "@hugeicons/core-free-icons/ArrowLeft01Icon";
import ArrowRight01Icon from "@hugeicons/core-free-icons/ArrowRight01Icon";
import ArrowUpDownIcon from "@hugeicons/core-free-icons/ArrowUpDownIcon";
import BotIcon from "@hugeicons/core-free-icons/BotIcon";
import Cancel01Icon from "@hugeicons/core-free-icons/Cancel01Icon";
import Chatting01Icon from "@hugeicons/core-free-icons/Chatting01Icon";
import CheckmarkCircle02Icon from "@hugeicons/core-free-icons/CheckmarkCircle02Icon";
import Loading03Icon from "@hugeicons/core-free-icons/Loading03Icon";
import SecurityCheckIcon from "@hugeicons/core-free-icons/SecurityCheckIcon";
import Task01Icon from "@hugeicons/core-free-icons/Task01Icon";
import TelegramIcon from "@hugeicons/core-free-icons/TelegramIcon";
import Tick02Icon from "@hugeicons/core-free-icons/Tick02Icon";
import type { ChannelIntegration } from "@/lib/api/types";
import { missingRequirements } from "./integration-model";

const text = {
  ru: {
    back: "К интеграциям", next: "Далее", previous: "Назад", steps: ["Бот", "Сервер", "Подключение"],
    titles: ["Какого бота подключаем?", "Проверим настройки сервера", "Подключение к Telegram"],
    intro: "Выберите бота бизнеса. Его токен команда заранее разместила на сервере — в браузере он не вводится и не показывается.",
    serverIntro: "Telegram присылает сообщения на публичный HTTPS-адрес Plumo. Все пункты ниже должны быть готовы на сервере.",
    connectIntro: "Plumo проверит бота, установит webhook и сохранит подключение. Ответы агента после подключения выключены — их включают отдельно, после проверки.",
    botSub: "Telegram Bot API · личные чаты", botText: "Клиенты пишут боту, обращения появляются в «Диалогах», агент отвечает в тот же чат.",
    tags: ["Личные чаты", "Webhook", "Ответы ИИ"],
    none: "Для этого бизнеса нет подготовленного бота. Создайте бота в @BotFather и попросите команду разместить токен на сервере.",
    howTo: "Как создать бота?", howToItems: ["Откройте @BotFather в Telegram и отправьте /newbot.", "Укажите имя и username, который заканчивается на bot.", "Передайте токен команде — его кладут в серверное окружение, не в эту форму."],
    benefits: ["Бот вашего бизнеса", "Диалоги в Plumo", "Агент по кнопке"],
    benefitTexts: ["Клиенты пишут боту, а не личному аккаунту сотрудника.", "Переписка, карточка клиента и передача менеджеру — в одном месте.", "Сначала проверяете входящие, затем включаете автоматические ответы."],
    need: "Вам понадобится", needItems: ["Бот, созданный в @BotFather", "Токен на сервере Plumo", "Второй аккаунт Telegram для проверки"],
    requirement: { public_url: "Публичный HTTPS-адрес API (PUBLIC_BASE_URL)", secret_key: "Ключ подписи webhook (CHANNEL_SECRET_KEY)", credentials_file: "Файл серверных конфигураций каналов" } as Record<string, string>,
    ready: "Готово", missing: "Не настроено", serverMissing: "Без этих настроек подключить бота нельзя. Их задаёт команда в backend/.env.",
    why: "Зачем это нужно", whyItems: ["HTTPS — Telegram отправляет webhook только на защищённый адрес.", "Ключ подписи — запросы от посторонних отклоняются до обработки.", "Конфигурации — токен хранится на сервере, кабинет выбирает его по имени."],
    review: "Ваш выбор", bot: "Бот", agent: "Ответы агента", agentOff: "Выключены после подключения", webhook: "Webhook", webhookText: "Будет указывать на этот сервер",
    connect: "Проверить и подключить", connecting: "Проверяем бота…", replace: "Заменить webhook",
    conflictHint: "Если это старый адрес Plumo (например, прежний туннель), замените его. Чужую настройку не трогайте.",
    next3: "Что произойдёт дальше", next3Items: ["Проверка бота (getMe)", "Проверка текущего webhook", "Установка webhook с секретом", "Тестовое сообщение боту", "Включение ответов агента"],
  },
  en: {
    back: "Back to integrations", next: "Next", previous: "Back", steps: ["Bot", "Server", "Connection"],
    titles: ["Which bot are we connecting?", "Let's check the server settings", "Connect to Telegram"],
    intro: "Choose the business bot. Its token was placed on the server by the team in advance — it is never typed or shown in the browser.",
    serverIntro: "Telegram delivers messages to a public HTTPS address of Plumo. Everything below must be ready on the server.",
    connectIntro: "Plumo checks the bot, sets the webhook and saves the connection. Agent replies are off after connecting — switch them on separately, after testing.",
    botSub: "Telegram Bot API · private chats", botText: "Customers message the bot, enquiries appear in Conversations, the agent replies in the same chat.",
    tags: ["Private chats", "Webhook", "AI replies"],
    none: "No bot is prepared for this business. Create a bot in @BotFather and ask the team to put its token on the server.",
    howTo: "How to create a bot?", howToItems: ["Open @BotFather in Telegram and send /newbot.", "Choose a name and a username ending with bot.", "Give the token to the team — it goes into the server environment, not this form."],
    benefits: ["Your business bot", "Conversations in Plumo", "Agent on a switch"],
    benefitTexts: ["Customers message the bot, not an employee's personal account.", "Chat, customer card and manager handoff in one place.", "Check incoming messages first, then switch automatic replies on."],
    need: "You will need", needItems: ["A bot created in @BotFather", "Its token on the Plumo server", "A second Telegram account for testing"],
    requirement: { public_url: "Public HTTPS address of the API (PUBLIC_BASE_URL)", secret_key: "Webhook signing key (CHANNEL_SECRET_KEY)", credentials_file: "Server channel configuration file" } as Record<string, string>,
    ready: "Ready", missing: "Not set", serverMissing: "The bot cannot be connected without these settings. The team sets them in backend/.env.",
    why: "Why this is needed", whyItems: ["HTTPS — Telegram sends webhooks only to a secure address.", "Signing key — requests from strangers are rejected before processing.", "Configurations — the token stays on the server; the workspace picks it by name."],
    review: "Your selection", bot: "Bot", agent: "Agent replies", agentOff: "Off after connecting", webhook: "Webhook", webhookText: "Will point to this server",
    connect: "Check and connect", connecting: "Checking the bot…", replace: "Replace webhook",
    conflictHint: "If this is an old Plumo address (e.g. a previous tunnel), replace it. Leave other systems' settings alone.",
    next3: "What happens next", next3Items: ["Bot check (getMe)", "Current webhook check", "Webhook set with a secret", "Test message to the bot", "Agent replies switched on"],
  },
};

const button = "inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 rounded-lg border-0 bg-plumo-blue px-4 py-2.5 font-[inherit] text-sm font-medium text-white transition-colors hover:bg-plumo-blue/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-not-allowed disabled:bg-plumo-line disabled:text-plumo-muted disabled:opacity-100";
const secondary = "inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 rounded-lg border border-solid border-plumo-line bg-white px-3 py-2 font-[inherit] text-sm text-plumo-ink hover:bg-plumo-line/30 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-not-allowed disabled:opacity-60";

function SetupPicture() {
  return <div aria-hidden="true" className="flex w-[70px] shrink-0 flex-col items-center justify-center gap-2 rounded-xl bg-plumo-blue/5 px-2 py-3 sm:w-[84px]">
    <span className="flex size-10 items-center justify-center rounded-xl bg-white text-plumo-blue/80"><PlumoIcon icon={TelegramIcon} size={24} /></span>
    <PlumoIcon icon={ArrowUpDownIcon} size={16} className="text-plumo-blue/50" />
    <span className="flex size-10 items-center justify-center rounded-xl bg-white text-plumo-blue/80"><PlumoIcon icon={AiChat02Icon} size={24} /></span>
  </div>;
}

function InfoCard({ title, children, icon = Task01Icon }: { title: string; children: ReactNode; icon?: typeof Task01Icon }) {
  return <div className="rounded-2xl border border-solid border-plumo-line bg-white p-5"><h2 className="m-0 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.12em] text-plumo-blue/80"><PlumoIcon icon={icon} size={18} />{title}</h2>{children}</div>;
}

type Notice = { tone: "ok" | "error"; text: string; conflict?: boolean } | null;

export function TelegramSetup({ item, busy, notice, onBack, onConnect }: {
  item: ChannelIntegration;
  busy: boolean;
  notice: Notice;
  onBack: () => void;
  onConnect: (credentialRef: string, replaceWebhook: boolean) => void;
}) {
  const { locale } = useLanguage();
  const c = text[locale];
  const [step, setStep] = useState(0);
  const [chosen, setChosen] = useState(item.credentials[0]?.ref ?? "");
  const titleRef = useRef<HTMLHeadingElement>(null);
  const paneRef = useRef<HTMLDivElement>(null);
  const missing = missingRequirements(item);
  const selected = item.credentials.find(option => option.ref === chosen);
  const canAdvance = step === 0 ? Boolean(selected) : step === 1 ? missing.length === 0 : false;
  const conflictHost = item.connection?.details.conflict_host;

  function go(next: number) {
    setStep(next);
    requestAnimationFrame(() => {
      if (paneRef.current) {
        paneRef.current.scrollTop = 0;
        paneRef.current.closest("section")?.scrollTo({ top: 0 });
      }
      titleRef.current?.focus({ preventScroll: true });
    });
  }
  const optionClass = (checked: boolean) => `relative flex cursor-pointer items-start gap-3 rounded-xl border border-solid p-4 transition-colors ${checked ? "border-plumo-blue/60 bg-plumo-soft/60" : "border-plumo-line bg-white hover:border-plumo-blue/30 hover:bg-plumo-soft/40"}`;
  const tick = (checked: boolean) => <span aria-hidden="true" className={`flex size-4 shrink-0 items-center justify-center rounded-full border border-solid ${checked ? "border-plumo-blue bg-plumo-blue text-white" : "border-plumo-line"}`}>{checked && <PlumoIcon icon={Tick02Icon} size={11} />}</span>;

  return <>
    <button type="button" className={`${secondary} mb-5`} onClick={onBack}><PlumoIcon icon={ArrowLeft01Icon} size={18} />{c.back}</button>
    <div className="grid overflow-hidden rounded-2xl border border-solid border-plumo-line bg-white lg:min-h-[650px] lg:grid-cols-[1.1fr_1fr]">
      <div className="flex min-w-0 flex-col">
        <div ref={paneRef} className="flex-1 p-6 sm:p-8 lg:max-h-[calc(100svh-270px)] lg:overflow-y-auto">
          <ol aria-label={locale === "ru" ? "Этапы подключения" : "Connection steps"} className="mb-7 mt-0 flex list-none items-center gap-2 p-0">{c.steps.map((label, index) => <li key={label} title={label} aria-current={index === step ? "step" : undefined} className={`h-2 rounded-full ${index === step ? "w-8 bg-plumo-blue" : "w-2 bg-plumo-line"}`}><span className="sr-only">{index + 1}. {label}</span></li>)}</ol>
          {step === 0 && <Image src="/images/channels/telegram.svg" alt="Telegram" width={36} height={36} className="mb-5" />}
          <h1 ref={titleRef} tabIndex={-1} className="m-0 text-[26px] font-normal leading-[1.25] tracking-tight outline-none sm:text-[30px]">{c.titles[step]}</h1>
          <p className="mb-6 mt-4 text-sm leading-6 text-plumo-muted">{step === 0 ? c.intro : step === 1 ? c.serverIntro : c.connectIntro}</p>

          {step === 0 && <>
            {item.credentials.length === 0 && <p className="m-0 rounded-xl bg-plumo-soft/70 p-4 text-[13px] leading-6 text-plumo-muted">{c.none}</p>}
            <fieldset className="m-0 space-y-3 border-0 p-0"><legend className="sr-only">{c.bot}</legend>{item.credentials.map(option => {
              const checked = chosen === option.ref;
              return <label key={option.ref} className={optionClass(checked)}><input type="radio" name="telegram-bot" checked={checked} onChange={() => setChosen(option.ref)} className="sr-only peer" /><span className="absolute inset-0 rounded-xl peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-plumo-blue" /><SetupPicture /><span className="min-w-0 flex-1"><span className="flex items-start justify-between gap-2"><span className="text-sm font-semibold">{option.label}</span>{tick(checked)}</span><span className="mt-1 block text-xs text-plumo-muted">{c.botSub}</span><span className="mt-2 block text-[13px] leading-6 text-plumo-muted">{c.botText}</span><span className="mt-3 flex flex-wrap gap-1">{c.tags.map(tag => <span key={tag} className="rounded-full bg-plumo-blue/5 px-2 py-0.5 text-[10px] text-plumo-blue/80">{tag}</span>)}</span></span></label>;
            })}</fieldset>
            <details className="mt-4 text-xs text-plumo-muted"><summary className="cursor-pointer rounded-sm py-2 focus-visible:outline-plumo-blue">{c.howTo}</summary><ol className="mb-0 mt-1 space-y-1 pl-5 leading-6">{c.howToItems.map(entry => <li key={entry}>{entry}</li>)}</ol></details>
          </>}

          {step === 1 && <>
            <ul className="m-0 list-none space-y-3 p-0">{Object.entries(item.requirements).map(([name, ok]) => <li key={name} className={`flex items-center gap-3 rounded-xl border border-solid p-4 ${ok ? "border-plumo-line bg-white" : "border-red-200 bg-red-50/60"}`}><span className={`flex size-9 shrink-0 items-center justify-center rounded-full ${ok ? "bg-plumo-blue/5 text-plumo-blue" : "bg-red-100 text-red-600"}`}><PlumoIcon icon={ok ? CheckmarkCircle02Icon : Cancel01Icon} size={20} /></span><span className="min-w-0 flex-1 text-sm">{c.requirement[name] ?? name}</span><span className={`text-xs ${ok ? "text-plumo-blue/80" : "text-red-700"}`}>{ok ? c.ready : c.missing}</span></li>)}</ul>
            {missing.length > 0 && <p className="mb-0 mt-4 text-xs leading-6 text-red-700">{c.serverMissing}</p>}
          </>}

          {step === 2 && <>
            <InfoCard title={c.review}><dl className="mb-0 mt-4 space-y-4">{[[c.bot, selected?.label ?? "—"], [c.webhook, c.webhookText], [c.agent, c.agentOff]].map(([label, value]) => <div key={label}><dt className="text-xs text-plumo-muted">{label}</dt><dd className="mb-0 ml-0 mt-1 text-sm">{value}</dd></div>)}</dl></InfoCard>
            {notice && <div role="alert" className={`mt-5 rounded-xl p-4 text-[13px] leading-6 ${notice.tone === "ok" ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800"}`}>
              <p className="m-0">{notice.text}{notice.conflict && conflictHost ? ` (${conflictHost})` : ""}</p>
              {notice.conflict && <><p className="mb-0 mt-2 text-xs">{c.conflictHint}</p><button type="button" className={`${secondary} mt-3`} disabled={busy} onClick={() => onConnect(chosen, true)}>{c.replace}</button></>}
            </div>}
            <button type="button" className={`${button} mt-5 w-full`} disabled={busy || !selected || missing.length > 0} onClick={() => onConnect(chosen, false)}>{busy ? <><PlumoIcon icon={Loading03Icon} size={18} className="animate-spin" />{c.connecting}</> : c.connect}</button>
          </>}
        </div>
        <div className="flex shrink-0 gap-2 border-0 border-t border-solid border-plumo-line bg-white p-4 sm:px-8">
          {step > 0 && <button type="button" className={secondary} disabled={busy} onClick={() => go(step - 1)}>{c.previous}</button>}
          {step < 2 && <button type="button" className={`${button} flex-1`} disabled={!canAdvance} onClick={() => go(step + 1)}>{c.next}<PlumoIcon icon={ArrowRight01Icon} size={18} /></button>}
        </div>
      </div>
      <aside className="flex flex-col justify-center gap-3 border-0 border-t border-solid border-plumo-blue/10 bg-plumo-soft/60 p-6 sm:p-8 lg:border-l lg:border-t-0">
        {step === 0 && <>{c.benefits.map((title, index) => <div key={title} className="flex items-start gap-3 rounded-2xl border border-solid border-plumo-line bg-white p-4"><span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-plumo-blue/5 text-plumo-blue"><PlumoIcon icon={[BotIcon, Chatting01Icon, AiChat02Icon][index]} size={22} /></span><div><h2 className="m-0 text-sm font-medium">{title}</h2><p className="mb-0 mt-1 text-xs leading-5 text-plumo-muted">{c.benefitTexts[index]}</p></div></div>)}<InfoCard title={c.need}><ul className="mb-0 mt-4 list-none space-y-3 p-0">{c.needItems.map(entry => <li key={entry} className="flex items-start gap-2 text-xs leading-5"><span className="mt-0.5 shrink-0 text-plumo-blue"><PlumoIcon icon={CheckmarkCircle02Icon} size={17} /></span>{entry}</li>)}</ul></InfoCard></>}
        {step === 1 && <InfoCard title={c.why} icon={SecurityCheckIcon}><ul className="mb-0 mt-4 list-none space-y-4 p-0">{c.whyItems.map(entry => <li key={entry} className="flex items-start gap-2 text-xs leading-5"><span className="mt-0.5 shrink-0 text-plumo-blue"><PlumoIcon icon={CheckmarkCircle02Icon} size={17} /></span>{entry}</li>)}</ul></InfoCard>}
        {step === 2 && <InfoCard title={c.next3}><ol className="mb-0 mt-4 space-y-4 pl-4 text-xs leading-6">{c.next3Items.map(entry => <li key={entry}>{entry}</li>)}</ol></InfoCard>}
      </aside>
    </div>
  </>;
}
