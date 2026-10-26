"use client";

import Image from "next/image";
import { useRef, useState } from "react";
import { useLanguage } from "@/lib/i18n";
import { PlumoIcon } from "@/components/ui/plumo-icon";
import ArrowLeft01Icon from "@hugeicons/core-free-icons/ArrowLeft01Icon";
import CheckmarkCircle02Icon from "@hugeicons/core-free-icons/CheckmarkCircle02Icon";
import type { ChannelIntegration } from "@/lib/api/types";

const button = "inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-xl border border-solid border-plumo-line bg-white px-5 py-3 font-[inherit] text-[14px] text-plumo-ink disabled:cursor-default disabled:opacity-50";
const primary = `${button} !border-plumo-ink !bg-plumo-ink !text-white`;

export function TelegramSetup({ item, busy, notice, onBack, onConnect }: { item: ChannelIntegration; busy: boolean; notice: { text: string; conflict?: boolean } | null; onBack: () => void; onConnect: (token: string, replace: boolean) => Promise<boolean> }) {
  const { locale } = useLanguage();
  const ru = locale === "ru";
  const [step, setStep] = useState(0);
  const [token, setToken] = useState("");
  const [visible, setVisible] = useState(false);
  const locked = useRef(false);
  const ready = Object.values(item.requirements).every(Boolean);
  const valid = /^[0-9]{5,20}:[A-Za-z0-9_-]{20,128}$/.test(token.trim());
  const titles = ru ? ["Создайте своего Telegram-бота", "Добавьте токен бота", "Подключите бота к Plumo"] : ["Create your Telegram bot", "Add the bot token", "Connect your bot to Plumo"];

  async function connect(replace = false) {
    if (locked.current || busy || !valid || !ready) return;
    locked.current = true;
    try { if (await onConnect(token.trim(), replace)) setToken(""); }
    finally { locked.current = false; }
  }

  return <div className="mx-auto max-w-[920px]">
    <button type="button" disabled={busy} onClick={onBack} className={`${button} mb-5`}><PlumoIcon icon={ArrowLeft01Icon} size={18} />{ru ? "К интеграциям" : "Back to integrations"}</button>
    <div className="grid overflow-hidden rounded-2xl border border-solid border-plumo-line bg-white lg:grid-cols-[1.1fr_1fr]">
      <div className="p-6 sm:p-8">
        <Image src="/images/channels/telegram.svg" alt="Telegram" width={40} height={40} />
        <p className="mb-2 mt-6 text-[12px] text-plumo-muted">{ru ? "Шаг" : "Step"} {step + 1}/3</p>
        <h1 className="m-0 text-[28px] font-medium tracking-tight">{titles[step]}</h1>
        {step === 0 && <><ol className="my-6 space-y-4 pl-5 text-[14px] leading-6"><li>{ru ? "Откройте официальный" : "Open the official"} <a href="https://t.me/BotFather" target="_blank" rel="noreferrer" className="text-plumo-blue underline">@BotFather</a>.</li><li>{ru ? "Отправьте /newbot, выберите название и имя с окончанием bot." : "Send /newbot and choose a name and a username ending in bot."}</li><li>{ru ? "Скопируйте выданный токен. Он понадобится на следующем шаге." : "Copy the token for the next step."}</li></ol><button type="button" onClick={() => setStep(1)} className={primary}>{ru ? "Бот готов — далее" : "My bot is ready — next"}</button></>}
        {step === 1 && <form className="mt-6 space-y-4" onSubmit={event => { event.preventDefault(); if (valid) setStep(2); }}><label className="flex flex-col gap-2 text-[14px]">{ru ? "Токен от BotFather" : "BotFather token"}<input name="telegram_bot_token" type={visible ? "text" : "password"} autoComplete="off" spellCheck={false} maxLength={160} value={token} onChange={event => setToken(event.target.value)} className="min-w-0 rounded-xl border border-solid border-plumo-line px-3 py-3 font-[inherit] text-[16px] text-plumo-ink" /></label><label className="flex items-center gap-2 text-[13px] text-plumo-muted"><input type="checkbox" checked={visible} onChange={event => setVisible(event.target.checked)} />{ru ? "Показать токен" : "Show token"}</label><p className="m-0 text-[12px] leading-5 text-plumo-muted">{ru ? "Токен хранится зашифрованно и повторно не показывается. Его можно заменить новым токеном из BotFather." : "The token is stored encrypted and is never shown again. You can replace it with a new BotFather token."}</p><div className="flex gap-2"><button type="button" className={button} onClick={() => setStep(0)}>{ru ? "Назад" : "Back"}</button><button type="submit" className={primary} disabled={!valid}>{ru ? "Далее" : "Next"}</button></div></form>}
        {step === 2 && <div className="mt-6 space-y-4"><p className="m-0 text-[14px] leading-6">{ru ? "Plumo проверит бота и настроит получение сообщений. Ответы агента останутся выключены до проверки подключения." : "Plumo will check your bot and set up incoming messages. Agent replies stay off until you verify the connection."}</p>{!ready && <p role="alert" className="rounded-xl bg-plumo-soft p-3 text-[13px]">{ru ? "Сервис ещё не готов к подключению Telegram. Обратитесь к команде Plumo." : "Telegram setup is not ready yet. Contact the Plumo team."}</p>}{notice && <div role="alert" className="rounded-xl bg-plumo-soft p-4 text-[13px] leading-6"><p className="m-0">{notice.text}</p>{notice.conflict && <><p>{ru ? "Бот уже подключён к другой системе. Замена webhook остановит получение сообщений там." : "This bot is already connected elsewhere. Replacing the webhook will stop incoming messages there."}</p><button type="button" className={button} disabled={busy} onClick={() => void connect(true)}>{ru ? "Заменить webhook и подключить" : "Replace webhook and connect"}</button></>}</div>}<div className="flex flex-wrap gap-2"><button type="button" disabled={busy} className={button} onClick={() => setStep(1)}>{ru ? "Изменить токен" : "Edit token"}</button><button type="button" disabled={busy || !ready || !valid} className={primary} onClick={() => void connect()}>{busy ? (ru ? "Подключаем…" : "Connecting…") : (ru ? "Подключить бота" : "Connect bot")}</button></div></div>}
      </div>
      <aside className="space-y-5 bg-plumo-soft/60 p-6 sm:p-8"><h2 className="m-0 text-[18px] font-medium">{ru ? "После подключения" : "After connecting"}</h2>{(ru ? ["Откройте бота по проверочной ссылке и нажмите «Запустить».", "Получите контрольное сообщение от Plumo.", "Вернитесь в кабинет и включите ответы агента."] : ["Open the verification link and press Start in Telegram.", "Receive a control message from Plumo.", "Return to your workspace and enable agent replies."]).map(text => <p key={text} className="m-0 flex gap-3 text-[14px] leading-6"><PlumoIcon icon={CheckmarkCircle02Icon} size={22} className="mt-0.5 shrink-0 text-plumo-blue" />{text}</p>)}</aside>
    </div>
  </div>;
}
