"use client";

import Image from "next/image";
import { useRef, useState, type ReactNode } from "react";
import { useLanguage } from "@/lib/i18n";
import { PlumoIcon } from "@/components/ui/plumo-icon";
import ArrowLeft01Icon from "@hugeicons/core-free-icons/ArrowLeft01Icon";
import ArrowRight01Icon from "@hugeicons/core-free-icons/ArrowRight01Icon";
import ArrowUpDownIcon from "@hugeicons/core-free-icons/ArrowUpDownIcon";
import Cancel01Icon from "@hugeicons/core-free-icons/Cancel01Icon";
import Chatting01Icon from "@hugeicons/core-free-icons/Chatting01Icon";
import CheckmarkCircle02Icon from "@hugeicons/core-free-icons/CheckmarkCircle02Icon";
import CloudIcon from "@hugeicons/core-free-icons/CloudIcon";
import ComputerIcon from "@hugeicons/core-free-icons/ComputerIcon";
import CreditCardIcon from "@hugeicons/core-free-icons/CreditCardIcon";
import HistoryIcon from "@hugeicons/core-free-icons/HistoryIcon";
import Megaphone01Icon from "@hugeicons/core-free-icons/Megaphone01Icon";
import Message01Icon from "@hugeicons/core-free-icons/Message01Icon";
import SmartPhone01Icon from "@hugeicons/core-free-icons/SmartPhone01Icon";
import Task01Icon from "@hugeicons/core-free-icons/Task01Icon";
import Tick02Icon from "@hugeicons/core-free-icons/Tick02Icon";
import { canAdvanceWhatsApp, nextWhatsAppStep, previousWhatsAppStep, type WhatsAppDraft } from "./whatsapp-setup-model";

const text = {
  ru: {
    back: "К интеграциям", next: "Далее", previous: "Назад", steps: ["Способ подключения", "Приложение", "Оплата", "Подключение"],
    titles: ["Какой WhatsApp подключаем?", "Этот номер в приложении WhatsApp Business?", "Как будете оплачивать WhatsApp?", "Подключение через Meta"],
    intro: "Выберите, как будете использовать номер: вместе с приложением на телефоне или через облачный API.",
    phone: "С приложением на телефоне", phoneSub: "WhatsApp Coexistence", phoneText: "Для номера из WhatsApp Business. Этот режим предусматривает работу приложения на телефоне вместе с бизнес-платформой.",
    cloud: "Без приложения, номер в облаке", cloudSub: "WhatsApp Business Platform (Cloud API)", cloudText: "Для отдельного номера, с которым планируете работать через Plumo. Использование номера и перенос согласуются при подключении.",
    tags: ["Приложение на телефоне", "Совместная работа", "История диалогов"], cloudTags: ["Облачный API", "Работа из Plumo"],
    difference: "В чём разница?", differenceText: "Coexistence предназначен для совместной работы приложения WhatsApp Business и API. Облачный вариант предназначен для работы через API. Доступность режима и импорта истории определяется при подключении Meta.",
    phoneBenefits: ["Приложение остаётся", "Диалоги в одном месте", "Перенос истории"], phoneDescriptions: ["Режим Coexistence сохраняет использование WhatsApp Business на телефоне.", "После подключения менеджер сможет работать с обращениями через Plumo.", "Возможность импорта проверяется при подключении аккаунта."],
    cloudBenefits: ["Отдельный номер", "Работа в Plumo", "Облачное подключение"], cloudDescriptions: ["Выделите номер для работы через бизнес-платформу.", "После подключения обращения будут доступны в диалогах.", "Регистрация номера выполняется через Meta."],
    need: "Вам понадобится", requirements: ["Телефон с WhatsApp Business", "Вход Facebook с доступом к бизнесу", "Доступ к номеру для подтверждения"], cloudRequirements: ["Номер для бизнес-платформы", "Вход Facebook с доступом к бизнесу", "Доступ к номеру для подтверждения"],
    appIntro: "Вариант с приложением на телефоне предназначен для WhatsApp Business. Если номер в обычном WhatsApp, сначала подготовьте переход в Business.",
    yes: "Да, номер в WhatsApp Business", yesText: "WhatsApp Business с этим номером установлен на телефоне.",
    no: "Нет, номер в обычном WhatsApp", noText: "Сначала перейдите в WhatsApp Business, затем продолжите подключение.",
    appHint: "Как отличить: у WhatsApp Business буква B на значке и инструменты для бизнеса в настройках.",
    appNeed: "Какое приложение нужно", appList: ["WhatsApp Business: буква B на значке", "Актуальная версия приложения", "Обычный WhatsApp: сначала подготовьте переход"],
    migration: "Подготовьте WhatsApp Business", migrationItems: ["Откройте официальную инструкцию по переходу.", "Установите WhatsApp Business и выполните переход по инструкции.", "Вернитесь сюда после завершения перехода."],
    download: "Открыть WhatsApp Business", migrated: "Номер уже перенесён в WhatsApp Business",
    paymentIntro: "Выберите предпочтительный способ расчётов. Стоимость зависит от категории сообщений, рынка и условий подключения.",
    meta: "Картой в Meta", metaText: "Оплата расходов WhatsApp напрямую в Meta. Платёжные данные вводятся на стороне Meta.",
    plumo: "По счёту от Plumo", plumoText: "Запросить расчёт через Plumo. Возможность и условия этого способа согласуем до подключения.",
    service: "Что такое сервисное сообщение", serviceText: "Ответ клиенту, который написал первым. Его последнее сообщение открывает 24-часовое окно для ответов.",
    ads: "Обращения из рекламы", adsText: "Для обращений из рекламы с переходом в WhatsApp у Meta предусмотрены отдельные условия тарификации.",
    costs: "Стоимость сообщений", costsMeta: "По тарифам Meta", costsPlumo: "После согласования", costsNote: "Расходы канала и тариф Plumo учитываются отдельно. Итоговую стоимость согласуем перед подключением.", rates: "Посмотреть тарифы Meta",
    connectIntro: "Следующий шаг — вход в Facebook, выбор бизнеса и подтверждение номера на стороне Meta.",
    connect: "Продолжить через Facebook", unavailable: "Подключение через Meta ещё не настроено.", save: "Сохранить параметры", saved: "Параметры сохранены. Канал ещё не подключён.",
    review: "Ваш выбор", method: "Способ подключения", app: "Приложение", payment: "Способ оплаты", connectNeed: "Что произойдёт дальше", connectList: ["Вход в Facebook", "Выбор бизнес-аккаунта", "Подтверждение номера", "Проверка подключения"],
  },
  en: {
    back: "Back to integrations", next: "Next", previous: "Back", steps: ["Connection method", "App", "Payment", "Connection"],
    titles: ["Which WhatsApp are we connecting?", "Is this number in the WhatsApp Business app?", "How will you pay for WhatsApp?", "Connect through Meta"],
    intro: "Choose whether to use the number with the app on your phone or through the cloud API.",
    phone: "With the app on the phone", phoneSub: "WhatsApp Coexistence", phoneText: "For a WhatsApp Business app number. This mode supports using the phone app alongside the business platform.",
    cloud: "No app, a number in the cloud", cloudSub: "WhatsApp Business Platform (Cloud API)", cloudText: "For a dedicated number you plan to use through Plumo. Number usage and migration are agreed during connection.",
    tags: ["Phone app", "Shared conversations", "Chat history"], cloudTags: ["Cloud API", "Replies from Plumo"],
    difference: "What is the difference?", differenceText: "Coexistence combines the WhatsApp Business app and the API. The cloud option is for API use. Availability and history import are determined during Meta onboarding.",
    phoneBenefits: ["The app stays", "Shared conversations", "History import"], phoneDescriptions: ["Coexistence keeps WhatsApp Business available on your phone.", "Once connected, a manager can handle enquiries in Plumo.", "Import availability is checked when connecting your account."],
    cloudBenefits: ["A dedicated number", "Work from Plumo", "Cloud connection"], cloudDescriptions: ["Use a number dedicated to the business platform.", "Once connected, enquiries appear in conversations.", "The number is registered through Meta."],
    need: "You will need", requirements: ["Your phone with WhatsApp Business", "A Facebook login with business access", "Access to the number for verification"], cloudRequirements: ["A number for the business platform", "A Facebook login with business access", "Access to the number for verification"],
    appIntro: "The option with the phone app is for WhatsApp Business. A number in regular WhatsApp needs to be prepared for migration first.",
    yes: "Yes, it is in WhatsApp Business", yesText: "WhatsApp Business with this number is installed on my phone.",
    no: "No, it is in regular WhatsApp", noText: "Move to WhatsApp Business before continuing the connection.",
    appHint: "How to tell: WhatsApp Business has a B on its icon and business tools in settings.",
    appNeed: "Which app you need", appList: ["WhatsApp Business: a B on the icon", "An up-to-date app version", "Regular WhatsApp: prepare migration first"],
    migration: "Prepare WhatsApp Business", migrationItems: ["Open the official migration instructions.", "Install WhatsApp Business and follow the migration instructions.", "Return here when the migration is complete."],
    download: "Open WhatsApp Business", migrated: "This number has been moved to WhatsApp Business",
    paymentIntro: "Choose your preferred payment method. Costs depend on message category, market and connection terms.",
    meta: "By card in Meta", metaText: "Pay WhatsApp expenses directly to Meta. Payment details are entered on Meta's side.",
    plumo: "By invoice from Plumo", plumoText: "Request billing through Plumo. Availability and terms will be agreed before connecting.",
    service: "What a service message is", serviceText: "A reply to a customer who messaged you first. Their latest message opens a 24-hour window for replies.",
    ads: "Chats from ads", adsText: "Meta has separate pricing conditions for enquiries from ads that click to WhatsApp.",
    costs: "Message costs", costsMeta: "Meta rates", costsPlumo: "To be agreed", costsNote: "Channel expenses and the Plumo plan are billed separately. Final costs will be agreed before connecting.", rates: "View Meta pricing",
    connectIntro: "Next, sign in to Facebook, choose your business and verify the number on Meta's side.",
    connect: "Continue with Facebook", unavailable: "Meta connection is not configured yet.", save: "Save settings", saved: "Settings saved. The channel is not connected yet.",
    review: "Your selection", method: "Connection method", app: "App", payment: "Payment method", connectNeed: "What happens next", connectList: ["Sign in to Facebook", "Choose a business account", "Verify the number", "Check the connection"],
  },
};

const button = "inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 rounded-lg border-0 bg-plumo-blue px-4 py-2.5 font-[inherit] text-sm font-medium text-white transition-colors hover:bg-plumo-blue/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue disabled:cursor-not-allowed disabled:bg-plumo-line disabled:text-plumo-muted disabled:opacity-100";
const secondary = "inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 rounded-lg border border-solid border-plumo-line bg-white px-3 py-2 font-[inherit] text-sm text-plumo-ink hover:bg-plumo-line/30 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue";

function SetupPicture({ cloud }: { cloud: boolean }) {
  return <div aria-hidden="true" className="flex w-[70px] shrink-0 flex-col items-center justify-center gap-2 rounded-xl bg-plumo-blue/5 px-2 py-3 sm:w-[84px]">
    <span className="flex size-10 items-center justify-center rounded-xl bg-white text-plumo-blue/80"><PlumoIcon icon={cloud ? CloudIcon : SmartPhone01Icon} size={26} /></span>
    <PlumoIcon icon={ArrowUpDownIcon} size={16} className="text-plumo-blue/50" />
    <span className="flex size-10 items-center justify-center rounded-xl bg-white text-plumo-blue/80"><PlumoIcon icon={Message01Icon} size={24} /></span>
  </div>;
}

function InfoCard({ title, children, payment = false }: { title: string; children: ReactNode; payment?: boolean }) {
  return <div className="rounded-2xl border border-solid border-plumo-line bg-white p-5"><h2 className="m-0 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.12em] text-plumo-blue/80"><PlumoIcon icon={payment ? CreditCardIcon : Task01Icon} size={18} />{title}</h2>{children}</div>;
}

export function WhatsAppSetup({ draft, onChange, onBack, onSave }: { draft: WhatsAppDraft; onChange: (draft: WhatsAppDraft) => void; onBack: () => void; onSave: () => void }) {
  const { locale } = useLanguage();
  const c = text[locale];
  const [step, setStep] = useState(0);
  const [saved, setSaved] = useState(false);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const paneRef = useRef<HTMLDivElement>(null);
  const phone = draft.method === "business-app";
  const benefits = phone ? c.phoneBenefits : c.cloudBenefits;
  const descriptions = phone ? c.phoneDescriptions : c.cloudDescriptions;
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
  function update(values: Partial<WhatsAppDraft>) { onChange({ ...draft, ...values }); setSaved(false); }
  const optionClass = (checked: boolean) => `relative flex cursor-pointer items-start gap-3 rounded-xl border border-solid p-4 transition-colors ${checked ? "border-plumo-blue/60 bg-plumo-soft/60" : "border-plumo-line bg-white hover:border-plumo-blue/30 hover:bg-plumo-soft/40"}`;
  const tick = (checked: boolean) => <span aria-hidden="true" className={`flex size-4 shrink-0 items-center justify-center rounded-full border border-solid ${checked ? "border-plumo-blue bg-plumo-blue text-white" : "border-plumo-line"}`}>{checked && <PlumoIcon icon={Tick02Icon} size={11} />}</span>;

  return <>
    <button type="button" className={`${secondary} mb-5`} onClick={onBack}><PlumoIcon icon={ArrowLeft01Icon} size={18} />{c.back}</button>
    <div className="grid overflow-hidden rounded-2xl border border-solid border-plumo-line bg-white lg:min-h-[650px] lg:grid-cols-[1.1fr_1fr]">
      <div className="flex min-w-0 flex-col">
        <div ref={paneRef} className="flex-1 p-6 sm:p-8 lg:max-h-[calc(100svh-270px)] lg:overflow-y-auto">
          <ol aria-label={locale === "ru" ? "Этапы подключения" : "Connection steps"} className="mb-7 mt-0 flex list-none items-center gap-2 p-0">{c.steps.map((label, index) => <li key={label} title={label} aria-current={index === step ? "step" : undefined} className={`h-2 rounded-full ${index === step ? "w-8 bg-plumo-blue" : "w-2 bg-plumo-line"}`}><span className="sr-only">{index + 1}. {label}</span></li>)}</ol>
          {step === 0 && <Image src="/images/channels/whatsapp-business.png" alt="WhatsApp Business" width={36} height={36} className="mb-5" />}
          <h1 ref={titleRef} tabIndex={-1} className="m-0 text-[26px] font-normal leading-[1.25] tracking-tight outline-none sm:text-[30px]">{c.titles[step]}</h1>
          <p className="mb-6 mt-4 text-sm leading-6 text-plumo-muted">{step === 0 ? c.intro : step === 1 ? c.appIntro : step === 2 ? c.paymentIntro : c.connectIntro}</p>
          {step === 0 && <>
            <fieldset className="m-0 space-y-3 border-0 p-0"><legend className="sr-only">{c.method}</legend>{(["business-app", "cloud"] as const).map(method => {
              const checked = draft.method === method;
              return <label key={method} className={optionClass(checked)}><input type="radio" name="whatsapp-method" checked={checked} onChange={() => update({ method })} className="sr-only peer" /><span className="absolute inset-0 rounded-xl peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-plumo-blue" /><SetupPicture cloud={method === "cloud"} /><span className="min-w-0 flex-1"><span className="flex items-start justify-between gap-2"><span className="text-sm font-semibold">{method === "business-app" ? c.phone : c.cloud}</span>{tick(checked)}</span><span className="mt-1 block text-xs text-plumo-muted">{method === "business-app" ? c.phoneSub : c.cloudSub}</span><span className="mt-2 block text-[13px] leading-6 text-plumo-muted">{method === "business-app" ? c.phoneText : c.cloudText}</span><span className="mt-3 flex flex-wrap gap-1">{(method === "business-app" ? c.tags : c.cloudTags).map(tag => <span key={tag} className="rounded-full bg-plumo-blue/5 px-2 py-0.5 text-[10px] text-plumo-blue/80">{tag}</span>)}</span></span></label>;
            })}</fieldset>
            <details className="mt-4 text-xs text-plumo-muted"><summary className="cursor-pointer rounded-sm py-2 focus-visible:outline-plumo-blue">{c.difference}</summary><p className="mb-0 mt-1 leading-6">{c.differenceText}</p></details>
          </>}
          {step === 1 && <>
            <fieldset className="m-0 space-y-3 border-0 p-0"><legend className="sr-only">{c.app}</legend>{(["business", "personal"] as const).map(app => <label key={app} className={optionClass(draft.app === app)}><input type="radio" name="whatsapp-app" checked={draft.app === app} onChange={() => update({ app, migrated: false })} className="mt-1 accent-plumo-blue" /><span><span className="block text-sm font-medium">{app === "business" ? c.yes : c.no}</span><span className="mt-1 block text-xs leading-6 text-plumo-muted">{app === "business" ? c.yesText : c.noText}</span></span></label>)}</fieldset>
            <p className="mt-4 text-xs leading-6 text-plumo-muted">{c.appHint}</p>
            {draft.app === "personal" && <div className="mt-5 rounded-xl bg-plumo-soft/70 p-4"><h2 className="m-0 text-sm font-medium">{c.migration}</h2><ol className="mb-4 mt-3 space-y-2 pl-5 text-xs leading-6 text-plumo-muted">{c.migrationItems.map(item => <li key={item}>{item}</li>)}</ol><a href="https://www.whatsapp.com/business/" target="_blank" rel="noopener noreferrer" className="text-xs text-plumo-blue underline underline-offset-4">{c.download}</a><label className="mt-4 flex cursor-pointer items-start gap-2 text-xs leading-5"><input type="checkbox" checked={draft.migrated} onChange={event => update({ migrated: event.target.checked })} className="mt-1 accent-plumo-blue" />{c.migrated}</label></div>}
          </>}
          {step === 2 && <>
            <fieldset className="m-0 space-y-3 border-0 p-0"><legend className="sr-only">{c.payment}</legend>{(["meta", "plumo"] as const).map(payment => <label key={payment} className={optionClass(draft.payment === payment)}><input type="radio" name="whatsapp-payment" checked={draft.payment === payment} onChange={() => update({ payment })} className="mt-1 accent-plumo-blue" /><span><span className="block text-sm font-medium">{payment === "meta" ? c.meta : c.plumo}</span><span className="mt-1 block text-xs leading-6 text-plumo-muted">{payment === "meta" ? c.metaText : c.plumoText}</span></span></label>)}</fieldset>
            <div className="mt-6 space-y-5 border-0 border-t border-solid border-plumo-line pt-5">{[[c.service, c.serviceText], [c.ads, c.adsText]].map(([title, description], index) => <div key={title} className="flex gap-3"><span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-plumo-blue/5 text-plumo-blue"><PlumoIcon icon={index === 0 ? Message01Icon : Megaphone01Icon} size={20} /></span><div><h2 className="m-0 text-xs font-semibold">{title}</h2><p className="mb-0 mt-1 text-xs leading-6 text-plumo-muted">{description}</p></div></div>)}</div>
          </>}
          {step === 3 && <>
            <InfoCard title={c.review}><dl className="mb-0 mt-4 space-y-4">{[[c.method, phone ? c.phone : c.cloud], ...(phone ? [[c.app, "WhatsApp Business"]] : []), [c.payment, draft.payment === "meta" ? c.meta : c.plumo]].map(([label, value]) => <div key={label}><dt className="text-xs text-plumo-muted">{label}</dt><dd className="mb-0 ml-0 mt-1 text-sm">{value}</dd></div>)}</dl></InfoCard>
            <p id="meta-unavailable" className="mb-0 mt-5 text-xs leading-6 text-plumo-muted">{c.unavailable}</p>
            <button type="button" className={`${button} mt-3 w-full`} disabled aria-describedby="meta-unavailable">{c.connect}</button>
            <p role="status" className="mb-0 mt-4 text-xs leading-6 text-plumo-muted">{saved ? c.saved : ""}</p>
          </>}
        </div>
        <div className="flex shrink-0 gap-2 border-0 border-t border-solid border-plumo-line bg-white p-4 sm:px-8">
          {step > 0 && <button type="button" className={secondary} onClick={() => go(previousWhatsAppStep(step, draft))}>{c.previous}</button>}
          {step < 3 ? <button type="button" className={`${button} flex-1`} disabled={!canAdvanceWhatsApp(step, draft)} onClick={() => go(nextWhatsAppStep(step, draft))}>{c.next}<PlumoIcon icon={ArrowRight01Icon} size={18} /></button> : <button type="button" className={`${button} flex-1`} disabled={saved} onClick={() => { onSave(); setSaved(true); }}>{c.save}</button>}
        </div>
      </div>
      <aside className="flex flex-col justify-center gap-3 border-0 border-t border-solid border-plumo-blue/10 bg-plumo-soft/60 p-6 sm:p-8 lg:border-l lg:border-t-0">
        {step === 0 && <>{benefits.map((title, index) => <div key={title} className="flex items-start gap-3 rounded-2xl border border-solid border-plumo-line bg-white p-4"><span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-plumo-blue/5 text-plumo-blue"><PlumoIcon icon={phone ? [SmartPhone01Icon, Chatting01Icon, HistoryIcon][index] : [SmartPhone01Icon, ComputerIcon, CloudIcon][index]} size={22} /></span><div><h2 className="m-0 text-sm font-medium">{title}</h2><p className="mb-0 mt-1 text-xs leading-5 text-plumo-muted">{descriptions[index]}</p></div></div>)}<InfoCard title={c.need}><ul className="mb-0 mt-4 list-none space-y-3 p-0">{(phone ? c.requirements : c.cloudRequirements).map(item => <li key={item} className="flex items-start gap-2 text-xs leading-5"><span className="mt-0.5 shrink-0 text-plumo-blue"><PlumoIcon icon={CheckmarkCircle02Icon} size={17} /></span>{item}</li>)}</ul></InfoCard></>}
        {step === 1 && <InfoCard title={c.appNeed}><ul className="mb-0 mt-4 list-none space-y-4 p-0">{c.appList.map((item, index) => <li key={item} className="flex items-start gap-2 text-xs leading-5"><span className={`mt-0.5 shrink-0 ${index === 2 ? "text-red-500" : "text-plumo-blue"}`}><PlumoIcon icon={index === 2 ? Cancel01Icon : CheckmarkCircle02Icon} size={17} /></span>{item}</li>)}</ul></InfoCard>}
        {step === 2 && <InfoCard title={c.costs} payment><dl className="mb-4 mt-5 space-y-4 text-sm"><div className="flex flex-wrap justify-between gap-2"><dt>{c.meta}</dt><dd className="m-0 text-plumo-muted">{c.costsMeta}</dd></div><div className="flex flex-wrap justify-between gap-2"><dt>{c.plumo}</dt><dd className="m-0 text-plumo-muted">{c.costsPlumo}</dd></div></dl><p className="mb-4 mt-0 border-0 border-t border-solid border-plumo-line pt-4 text-xs leading-6 text-plumo-muted">{c.costsNote}</p><a href="https://whatsappbusiness.com/products/platform-pricing/" target="_blank" rel="noopener noreferrer" className="text-xs text-plumo-blue underline underline-offset-4">{c.rates}</a></InfoCard>}
        {step === 3 && <InfoCard title={c.connectNeed}><ol className="mb-0 mt-4 space-y-4 pl-4 text-xs leading-6">{c.connectList.map(item => <li key={item}>{item}</li>)}</ol></InfoCard>}
      </aside>
    </div>
  </>;
}
