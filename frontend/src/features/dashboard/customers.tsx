"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, goToLogin } from "@/lib/api/client";
import { usePolling } from "@/lib/api/use-polling";
import { useLanguage } from "@/lib/i18n";
import { CustomerHistory } from "./customer-history";
import { apiErrorText } from "./api-messages";
import { channelName, formatTime } from "./dialogue-model";
import { conversationHref, customerHref, dashboardCustomer } from "./navigation";

type Customer = { id: string; name: string | null; handle: string | null; phone: string | null; contact_phone: string | null; language: string; need: string | null; channels: string[]; created_at: string };
type CustomerPage = { items: Customer[]; next_cursor: string | null };
type Card = Customer;
const button = "cursor-pointer rounded-lg border border-solid border-plumo-line bg-white px-3 py-2 font-[inherit] text-sm text-plumo-ink hover:bg-plumo-soft focus-visible:outline-2 focus-visible:outline-plumo-blue disabled:cursor-default disabled:opacity-50";

export function Customers({ active }: { active: boolean }) {
  const { locale } = useLanguage();
  const ru = locale === "ru";
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [channel, setChannel] = useState("");
  const filterKey = `${query}|${channel}`;
  const [pages, setPages] = useState<{ key: string; cursors: string[] }>({ key: "", cursors: [] });
  const cursors = pages.key === filterKey ? pages.cursors : [];
  const cursor = cursors.at(-1);
  const requestKey = `${filterKey}|${cursor ?? ""}`;
  const [data, setData] = useState<CustomerPage | null>(null);
  const [loadedKey, setLoadedKey] = useState("");
  const [listError, setListError] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [card, setCard] = useState<Card | null>(null);
  const [cardError, setCardError] = useState("");
  const [cardRetry, setCardRetry] = useState(0);
  useEffect(() => { const timer = setTimeout(() => setQuery(search.trim()), 300); return () => clearTimeout(timer); }, [search]);
  useEffect(() => {
    if (!active) return;
    const read = () => setSelected(dashboardCustomer(window.location.search));
    read(); window.addEventListener("popstate", read);
    return () => window.removeEventListener("popstate", read);
  }, [active]);
  const load = useCallback(async (signal: AbortSignal) => {
    setLoading(true);
    try {
      const value = await api<CustomerPage>("customers", { query: { q: query, channel, cursor, limit: 30 }, signal });
      if (!signal.aborted) { setData(value); setLoadedKey(`${query}|${channel}|${cursor ?? ""}`); setListError(""); }
    } catch (error) {
      if (signal.aborted) return;
      if (error instanceof ApiError && error.unauthenticated) goToLogin();
      setListError(error instanceof ApiError ? apiErrorText(error.code, locale) : ru ? "Не удалось загрузить клиентов." : "Could not load customers.");
      throw error;
    } finally { if (!signal.aborted) setLoading(false); }
  }, [query, channel, cursor, locale, ru]);
  const refresh = usePolling(load, 15000, `${filterKey}|${cursor ?? ""}`, active);
  useEffect(() => {
    setCard(null); setCardError("");
    if (!selected || !active) return;
    const controller = new AbortController();
    api<Card>(`customers/${selected}`, { signal: controller.signal }).then(
      value => { if (!controller.signal.aborted) setCard(value); },
      error => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.unauthenticated) goToLogin();
        setCardError(error instanceof ApiError ? apiErrorText(error.code, locale) : ru ? "Не удалось открыть карточку." : "Could not open the customer.");
      });
    return () => controller.abort();
  }, [selected, active, cardRetry, locale, ru]);
  function select(id: string | null) {
    window.history.pushState(null, "", id ? customerHref(id) : "/dashboard#customers");
    setSelected(id);
  }
  const visibleData = loadedKey === requestKey ? data : null;
  const name = (value: Pick<Customer, "name" | "handle" | "phone">) => value.name || value.handle || value.phone || (ru ? "Клиент без имени" : "Unnamed customer");
  const languages: Record<string, string> = ru ? { ru: "Русский", ky: "Кыргызский", mixed: "Смешанный", unknown: "Не определён" } : { ru: "Russian", ky: "Kyrgyz", mixed: "Mixed", unknown: "Unknown" };
  const current = card?.id === selected ? card : null;
  return <section aria-label={ru ? "Клиенты" : "Customers"} className="h-full overflow-y-auto p-4 text-plumo-ink md:p-6"><div className="mx-auto max-w-6xl">
    <h1 className="m-0 text-xl font-semibold">{ru ? "Клиенты" : "Customers"}</h1>
    <p className="mb-4 mt-2 text-sm leading-6 text-plumo-muted">{ru ? "Клиенты из обращений в ваши каналы. Совпадение телефона не объединяет карточки. Новые клиенты показаны первыми." : "Customers from channel conversations. Matching phone numbers do not merge records. Newest customers first."}</p>
    <div className="mb-4 flex flex-wrap gap-2">
      <input type="search" aria-label={ru ? "Поиск клиентов" : "Search customers"} placeholder={ru ? "Имя, контакт или телефон" : "Name, contact or phone"} maxLength={100} value={search} onChange={event => setSearch(event.target.value)} className="min-w-0 flex-1 rounded-lg border border-solid border-plumo-line bg-white px-3 py-2 font-[inherit] text-base focus:outline-plumo-blue" />
      <select aria-label={ru ? "Канал клиента" : "Customer channel"} value={channel} onChange={event => setChannel(event.target.value)} className={button}><option value="">{ru ? "Все каналы" : "All channels"}</option>{["telegram", "instagram", "whatsapp", "voice", "cli"].map(value => <option key={value} value={value}>{channelName(value)}</option>)}</select>
      <button type="button" className={button} onClick={refresh}>{ru ? "Обновить" : "Refresh"}</button>
    </div>
    {listError && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">{listError} {ru ? "Ранее загруженные данные могут быть устаревшими." : "Previously loaded data may be out of date."}</p>}
    <div className="grid gap-4 lg:grid-cols-2"><div className={selected ? "hidden lg:block" : "block"}>
      {loading && <p role="status" className="text-sm text-plumo-muted">{ru ? "Загружаем…" : "Loading…"}</p>}
      {!loading && !listError && visibleData?.items.length === 0 && <p className="rounded-xl border border-solid border-plumo-line bg-white p-6 text-sm">{query || channel ? (ru ? "Клиенты не найдены. Измените поиск или канал." : "No customers found. Change the search or channel.") : (ru ? "Пока нет клиентов. Они появятся после обращения в подключённый канал." : "No customers yet. They appear after a message in a connected channel.")}</p>}
      <div className="space-y-2">{visibleData?.items.map(item => <button key={item.id} type="button" aria-current={selected === item.id ? "true" : undefined} className={`${button} block w-full p-4 text-left ${selected === item.id ? "!bg-plumo-soft" : ""}`} onClick={() => select(item.id)}><span className="block break-words font-medium">{name(item)}</span><span className="mt-1 block break-words text-xs leading-5 text-plumo-muted">{item.handle || item.phone || "—"} · {item.channels.map(channelName).join(", ") || "—"}</span>{item.contact_phone && <span className="mt-1 block text-xs text-plumo-muted">{ru ? "Номер со слов клиента (не проверен)" : "Customer-provided phone (unverified)"}: {item.contact_phone}</span>}</button>)}</div>
      <div className="mt-4 flex items-center justify-between gap-2"><button type="button" disabled={!cursors.length || loading} className={button} onClick={() => setPages({ key: filterKey, cursors: cursors.slice(0, -1) })}>{ru ? "Предыдущая" : "Previous"}</button><span className="text-xs text-plumo-muted">{ru ? "Страница" : "Page"} {cursors.length + 1}</span><button type="button" disabled={!visibleData?.next_cursor || loading} className={button} onClick={() => { if (visibleData?.next_cursor) setPages({ key: filterKey, cursors: [...cursors, visibleData.next_cursor] }); }}>{ru ? "Следующая" : "Next"}</button></div>
    </div>
    {selected && <div className="min-w-0 rounded-xl border border-solid border-plumo-line bg-white p-4"><button type="button" className={button} onClick={() => select(null)}>{ru ? "К списку клиентов" : "Back to customers"}</button>
      {cardError ? <div role="alert" className="mt-4 text-sm"><p>{cardError}</p><button type="button" className={button} onClick={() => setCardRetry(value => value + 1)}>{ru ? "Повторить" : "Retry"}</button></div> : !current ? <p role="status" className="text-sm">{ru ? "Открываем карточку…" : "Opening customer…"}</p> : <>
        <h2 className="mb-0 mt-5 break-words text-lg font-semibold">{name(current)}</h2>
        <p className="text-xs text-plumo-muted">{current.handle || ""} · {current.channels.map(channelName).join(", ") || "—"}</p><dl className="space-y-3 text-sm leading-6">{current.phone && <div><dt className="text-plumo-muted">{ru ? "Номер из канала" : "Channel phone"}</dt><dd className="m-0 break-words">{current.phone}</dd></div>}{current.contact_phone && <div><dt className="text-plumo-muted">{ru ? "Номер со слов клиента (не проверен)" : "Customer-provided phone (unverified)"}</dt><dd className="m-0 break-words">{current.contact_phone}</dd></div>}<div><dt className="text-plumo-muted">{ru ? "Язык" : "Language"}</dt><dd className="m-0">{languages[current.language] ?? current.language}</dd></div>{current.need && <div><dt className="text-plumo-muted">{ru ? "Потребность" : "Customer need"}</dt><dd className="m-0 break-words">{current.need}</dd></div>}<div><dt className="text-plumo-muted">{ru ? "Создан" : "Created"}</dt><dd className="m-0">{formatTime(current.created_at, locale)}</dd></div></dl>
        <CustomerHistory key={selected} customerId={selected} locale={locale} initiallyOpen showSummary openConversation={item => window.location.assign(conversationHref(item.id))} />
      </>}
    </div>}
    </div>
  </div></section>;
}
