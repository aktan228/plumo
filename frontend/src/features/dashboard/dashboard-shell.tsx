"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { LanguageSwitch, useLanguage } from "@/lib/i18n";
import { DashboardIcon, type DashboardIconName } from "./dashboard-icon";
import { Dialogues } from "./dialogues";
import { Integrations } from "./integrations";
import { ChatBoard } from "./chat-board";
import { SoonDialog } from "./soon-dialog";

const groups = [
  { ru: "Основное", en: "Main", items: [
    { id: "chats", ru: "Диалоги", en: "Chats", icon: "chat" },
    { id: "knowledge", ru: "База знаний", en: "Knowledge Base", icon: "book" },
    { id: "testing", ru: "Тестирование", en: "Testing", icon: "testing" },
    { id: "improvement", ru: "Улучшения", en: "Improvement", icon: "edit" },
    { id: "broadcasts", ru: "Рассылки", en: "Broadcasts", icon: "broadcast" },
    { id: "scenarios", ru: "Сценарии", en: "Scenarios", icon: "bolt" },
    { id: "settings", ru: "Настройки", en: "Settings", icon: "settings" },
  ] },
  { ru: "Аналитика", en: "Analytics", items: [
    { id: "statistics", ru: "Статистика", en: "Statistics", icon: "statistics" },
    { id: "customers", ru: "Клиенты", en: "Customers", icon: "customers" },
  ] },
  { ru: "Интеграции", en: "Integrations", items: [
    { id: "integrations", ru: "Интеграции", en: "Integrations", icon: "integrations" },
    { id: "extensions", ru: "Расширения", en: "Extensions", icon: "extensions" },
    { id: "tools", ru: "Инструменты", en: "Tools", icon: "tools" },
    { id: "voice", ru: "Голосовой агент", en: "Voice Agent", icon: "voice" },
  ] },
] as const;
const pages = groups.flatMap(group => [...group.items]);
type View = typeof pages[number]["id"];
const actions: { ru: string; en: string; icon: DashboardIconName }[] = [
  { ru: "Фильтры", en: "Filters", icon: "filter" },
  { ru: "Добавить диалог", en: "Add chat", icon: "add" },
  { ru: "Поиск", en: "Search", icon: "search" },
  { ru: "Сценарии", en: "Scenarios", icon: "branch" },
  { ru: "Оформление", en: "Appearance", icon: "appearance" },
  { ru: "Добавить клиента", en: "Add customer", icon: "userAdd" },
  { ru: "Справка", en: "Help", icon: "help" },
];
const controlClass = "flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-md border-0 bg-transparent p-1 text-plumo-muted transition-colors hover:bg-plumo-line/65 hover:text-plumo-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue";

export function DashboardShell() {
  const { locale, t } = useLanguage();
  const [collapsed, setCollapsed] = useState(false);
  const [view, setView] = useState<View>("chats");
  const [layout, setLayout] = useState<"kanban" | "list">("kanban");
  const [soon, setSoon] = useState(false);
  const c = locale === "ru" ? {
    menu: "Навигация", collapse: "Свернуть панель", expand: "Развернуть панель",
    disabled: "Ответы ИИ отключены", description: "Продолжайте обучать и тестировать ИИ-агента. Включите ответы клиентам, когда будете готовы.",
    enable: "Включить ИИ", period: "Период", kanban: "Канбан", list: "Список", more: "Ещё",
    trial: "Пробный период", subscription: "Купить подписку", telegram: "Наш Telegram", help: "Помощь",
  } : {
    menu: "Navigation", collapse: "Collapse sidebar", expand: "Expand sidebar",
    disabled: "AI replies are disabled", description: "Keep training and testing your AI agent. Enable customer replies when you are ready.",
    enable: "Turn the AI on", period: "Date range", kanban: "Kanban", list: "List", more: "More options",
    trial: "Trial period", subscription: "Buy subscription", telegram: "Join our Telegram", help: "Help",
  };
  const title = pages.find(page => page.id === view)?.[locale];

  useEffect(() => {
    const readHash = () => {
      const hash = window.location.hash.slice(1);
      setView(pages.find(page => page.id === hash)?.id ?? "chats");
    };
    readHash();
    window.addEventListener("hashchange", readHash);
    return () => window.removeEventListener("hashchange", readHash);
  }, []);

  function navigate(next: View) {
    setView(next);
    window.location.hash = next;
  }

  function navigation(mobile = false) {
    const compact = collapsed && !mobile;
    return groups.map(group => <div key={group.en} className="mb-2">
      <button type="button" onClick={() => setSoon(true)} title={compact ? group[locale] : undefined} aria-label={group[locale]} className={`flex h-6 cursor-pointer items-center gap-1 border-0 bg-transparent px-1 text-[10.5px] text-plumo-muted focus-visible:outline-2 focus-visible:outline-plumo-blue ${compact ? "w-full justify-center" : ""}`}>
        {compact ? <span aria-hidden="true">···</span> : <>{group[locale]}<DashboardIcon name="chevron" size={8} /></>}
      </button>
      {group.items.map(item => <button key={item.id} type="button" aria-current={view === item.id ? "page" : undefined} aria-label={item[locale]} title={compact ? item[locale] : undefined} onClick={event => {
        navigate(item.id);
        event.currentTarget.closest("details")?.removeAttribute("open");
      }} className={`flex h-7 w-full cursor-pointer items-center gap-1.5 rounded-[4px] border-0 px-3 text-left font-[inherit] text-[11.5px] text-plumo-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-plumo-blue ${view === item.id ? "bg-plumo-ink/[0.065]" : "bg-transparent hover:bg-plumo-ink/[0.04]"} ${compact ? "justify-center px-0" : ""}`}>
        <span className="flex shrink-0 text-plumo-ink/75"><DashboardIcon name={item.icon} size={16} /></span>{!compact && <span className="truncate">{item[locale]}</span>}
      </button>)}
    </div>);
  }

  return <div className="flex h-dvh min-h-[480px] overflow-hidden bg-plumo-line text-plumo-ink md:pb-1.5 md:pr-1.5 md:pt-2.5">
    <a href="#workspace" className="skip-link">{t.skip}</a>
    <aside aria-label={c.menu} className={`hidden h-full shrink-0 flex-col overflow-y-auto px-1.5 transition-[width] duration-200 md:flex [scrollbar-width:thin] ${collapsed ? "w-[52px]" : "w-[150px]"}`}>
      <div className={`flex h-[42px] shrink-0 items-start pt-1 ${collapsed ? "justify-center" : "justify-between pl-2.5"}`}>
        {!collapsed && <Link href="/" aria-label={t.home} className="relative block h-6 w-[84px] shrink-0 overflow-hidden rounded-sm"><Image src="/images/plumo-logo.png" alt="Plumo" width={84} height={84} priority className="absolute -top-[32px] left-0 mix-blend-multiply" /></Link>}
        <button type="button" className={`${controlClass} mt-0.5 !size-5`} aria-label={collapsed ? c.expand : c.collapse} title={collapsed ? c.expand : c.collapse} aria-expanded={!collapsed} aria-controls="dashboard-nav" onClick={() => setCollapsed(value => !value)}><DashboardIcon name="panel" size={12} /></button>
      </div>
      <nav id="dashboard-nav" className="shrink-0">{navigation()}</nav>
      <div className="mt-1 flex flex-col pb-1">
        {!collapsed && <>
          <p className="mb-1 mt-0 px-1.5 text-[10.5px] leading-[14px] text-plumo-muted">{c.trial}</p>
          <button type="button" onClick={() => setSoon(true)} className="flex h-[30px] cursor-pointer items-center justify-center gap-1 rounded-[4px] border border-solid border-plumo-blue/25 bg-plumo-soft px-1 font-[inherit] text-[11px] text-plumo-ink hover:bg-plumo-blue/10 focus-visible:outline-2 focus-visible:outline-plumo-blue">{c.subscription}<DashboardIcon name="sparkles" size={14} /></button>
          <button type="button" onClick={() => setSoon(true)} className="mx-2 mb-1.5 mt-[7px] flex h-[27px] cursor-pointer items-center gap-1.5 rounded-md border-0 bg-plumo-blue/[0.07] px-1.5 text-[10.5px] text-plumo-ink hover:bg-plumo-blue/10 focus-visible:outline-2 focus-visible:outline-plumo-blue"><Image src="/images/channels/telegram.svg" alt="" width={18} height={18} /><span className="truncate">{c.telegram}</span></button>
        </>}
        <button type="button" aria-label={c.help} title={collapsed ? c.help : undefined} onClick={() => setSoon(true)} className={`flex h-7 cursor-pointer items-center gap-1.5 rounded-md border-0 bg-transparent px-3 text-left text-[11.5px] text-plumo-ink hover:bg-plumo-ink/[0.04] ${collapsed ? "justify-center px-0" : ""}`}><DashboardIcon name="help" size={16} />{!collapsed && c.help}</button>
        {!collapsed && <div className="mt-2 px-1 [&_button]:min-h-7 [&_button]:px-1.5 [&_button]:py-1 [&_button]:text-[9px]"><LanguageSwitch /></div>}
      </div>
    </aside>
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-[3px] bg-white">
      <header className="flex min-h-14 shrink-0 items-center gap-3 border-0 border-b border-solid border-plumo-line px-3 py-2.5 md:pl-[15px]">
        <span className="hidden text-plumo-muted sm:flex"><DashboardIcon name="pause" size={13} /></span>
        <div className="min-w-0 flex-1"><p className="m-0 text-xs font-semibold leading-[18px]">{c.disabled}</p><p className="m-0 hidden text-xs leading-[18px] text-plumo-muted sm:block">{c.description}</p></div>
        <button type="button" onClick={() => setSoon(true)} className="min-h-[25px] shrink-0 cursor-pointer rounded-lg border border-solid border-plumo-ink/80 bg-plumo-ink px-2 py-1 font-[inherit] text-[11px] text-white shadow-sm hover:bg-plumo-ink/85 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue">{c.enable}</button>
      </header>
      <main id="workspace" tabIndex={-1} aria-label={title} className="flex min-h-0 flex-1 flex-col bg-plumo-line/15 focus:outline-none">
        <div className="flex min-h-10 shrink-0 flex-wrap items-center gap-2 border-0 border-b border-solid border-plumo-line px-2.5 py-1 md:pl-3.5">
          <details className="relative z-20 md:hidden" onKeyDown={event => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
            <summary aria-label={c.menu} className={`${controlClass} list-none [&::-webkit-details-marker]:hidden`}><DashboardIcon name="menu" size={18} /></summary>
            <nav aria-label={c.menu} className="absolute left-0 top-9 max-h-[calc(100dvh-130px)] w-52 overflow-y-auto rounded-lg border border-solid border-plumo-line bg-white p-2 shadow-xl">
              {navigation(true)}
              <div className="border-0 border-t border-solid border-plumo-line pt-1"><LanguageSwitch /></div>
            </nav>
          </details>
          <h1 className="m-0 text-xs font-normal text-plumo-muted">{title}</h1>
          {view === "chats" && <>
            <button type="button" onClick={() => setSoon(true)} className="flex cursor-pointer items-center gap-1.5 rounded border-0 bg-transparent p-1 text-[10px] text-plumo-muted hover:text-plumo-ink"><DashboardIcon name="calendar" size={13} />{c.period}</button>
            <div role="group" aria-label={locale === "ru" ? "Инструменты диалогов" : "Chat tools"} className="flex items-center gap-0.5 max-sm:order-last max-sm:w-full">
              {actions.map(action => <button key={action.en} type="button" aria-label={action[locale]} title={action[locale]} className={controlClass} onClick={() => setSoon(true)}><DashboardIcon name={action.icon} size={14} /></button>)}
            </div>
            <div role="group" aria-label={locale === "ru" ? "Вид диалогов" : "Chat view"} className="ml-auto flex items-center rounded-lg bg-plumo-line/35 p-0.5">
              {(["kanban", "list"] as const).map(mode => <button key={mode} type="button" aria-pressed={layout === mode} onClick={() => setLayout(mode)} className={`flex h-[23px] cursor-pointer items-center gap-1 rounded-md border-0 px-2 font-[inherit] text-[10px] ${layout === mode ? "bg-white text-plumo-ink shadow-sm" : "bg-transparent text-plumo-muted hover:bg-white/60"}`}><DashboardIcon name={mode} size={12} />{c[mode]}</button>)}
            </div>
          </>}
          <button type="button" aria-label={c.more} title={c.more} onClick={() => setSoon(true)} className={`${controlClass} ${view !== "chats" ? "ml-auto" : ""}`}><DashboardIcon name="more" size={14} /></button>
        </div>
        <div className={view === "integrations" ? "min-h-0 flex-1" : "hidden"}><Integrations onDialogues={() => navigate("chats")} /></div>
        <div className={view === "chats" ? "min-h-0 flex-1" : "hidden"}>
          {layout === "kanban" ? <ChatBoard onSoon={() => setSoon(true)} /> : <Dialogues />}
        </div>
        {view !== "integrations" && view !== "chats" && <div className="flex flex-1 items-center justify-center text-base text-plumo-muted">soon</div>}
      </main>
    </div>
    <SoonDialog open={soon} onClose={() => setSoon(false)} />
  </div>;
}
