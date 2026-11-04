"use client";

import { useEffect, useState } from "react";
import { ApiError, api, goToLogin } from "@/lib/api/client";
import { apiErrorText } from "./api-messages";
import { channelName, formatTime, type Locale } from "./dialogue-model";

type History = {
  summary: { summary: string; need: string | null } | null;
  conversations: { id: string; channel: string; started_at: string; summary: string | null }[];
  messages: { id: string; conversation_id: string; role: string; text: string; timestamp: string }[];
};

export function CustomerHistory({ customerId, locale, openConversation, initiallyOpen = false, showSummary = false }: {
  customerId: string;
  locale: Locale;
  openConversation: (item: { id: string }) => void;
  initiallyOpen?: boolean;
  showSummary?: boolean;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  const [data, setData] = useState<History | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const ru = locale === "ru";
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setData(null);
    setError(null);
    api<History>(`customers/${customerId}/history`, { query: { limit: 100 }, signal: controller.signal }).then(
      value => { if (!controller.signal.aborted) setData(value); },
      reason => {
        if (controller.signal.aborted) return;
        if (reason instanceof ApiError) {
          if (reason.unauthenticated) goToLogin();
          setError(apiErrorText(reason.code, locale));
        } else setError(ru ? "Не удалось загрузить историю." : "Could not load history.");
      },
    );
    return () => controller.abort();
  }, [customerId, open, locale, retry, ru]);
  return <section className="mt-6 border-0 border-t border-solid border-plumo-line pt-4">
    <button type="button" aria-expanded={open} onClick={() => setOpen(value => !value)} className="cursor-pointer rounded border-0 bg-transparent p-1 font-[inherit] text-xs font-medium text-plumo-blue focus-visible:outline-2 focus-visible:outline-plumo-blue">
      {open ? (ru ? "Скрыть историю" : "Hide history") : (ru ? "История клиента" : "Customer history")}
    </button>
    {open && <div className="mt-3 space-y-3 text-xs leading-5">
      {error ? <div role="alert"><p>{error}</p><button type="button" onClick={() => setRetry(value => value + 1)} className="cursor-pointer rounded border border-solid border-plumo-line bg-white p-2 font-[inherit] text-plumo-blue">{ru ? "Повторить" : "Retry"}</button></div>
        : !data ? <p role="status">{ru ? "Загружаем историю…" : "Loading history…"}</p>
          : <>
            {showSummary && <div><h3 className="m-0 text-xs font-semibold">{ru ? "Краткое резюме" : "Summary"}</h3><p className="mb-3 mt-1 whitespace-pre-wrap break-words">{data.summary?.summary || (ru ? "Резюме пока нет." : "No summary yet.")}</p></div>}
            <h3 className="m-0 text-xs font-semibold">{ru ? "Диалоги этого клиента" : "This customer's conversations"}</h3>
            {data.conversations.map(item => <button key={item.id} type="button" onClick={() => openConversation(item)} className="block w-full cursor-pointer rounded-lg border border-solid border-plumo-line bg-white p-2 text-left font-[inherit] text-xs leading-5 text-plumo-blue hover:bg-plumo-soft focus-visible:outline-2 focus-visible:outline-plumo-blue">
              {channelName(item.channel)} · {formatTime(item.started_at, locale)}
              {item.summary && <span className="block text-plumo-muted">{item.summary}</span>}
            </button>)}
            <h3 className="m-0 text-xs font-semibold">{ru ? "Последние сообщения (до 100)" : "Recent messages (up to 100)"}</h3>
            {data.messages.length === 0 && <p>{ru ? "Сообщений пока нет." : "No messages yet."}</p>}
            {data.messages.map(item => <div key={item.id} className="rounded-lg bg-plumo-soft p-2">
              <p className="m-0 text-[10px] text-plumo-muted">{item.role === "user" ? (ru ? "Клиент" : "Customer") : item.role === "manager" ? (ru ? "Менеджер" : "Manager") : item.role === "assistant" ? "Plumo" : (ru ? "Событие" : "Event")} · {formatTime(item.timestamp, locale)}</p>
              <p className="mb-0 mt-1 whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{item.text}</p>
            </div>)}
          </>}
    </div>}
  </section>;
}
