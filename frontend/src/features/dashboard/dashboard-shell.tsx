"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { LanguageSwitch, useLanguage } from "@/lib/i18n";
import { DashboardIcon } from "./dashboard-icon";
import { Dialogues } from "./dialogues";
import { Customers } from "./customers";
import { Improvements } from "./improvements";
import { Statistics } from "./statistics";
import { Kanban } from "./kanban";
import { conversationHref, dashboardConversation } from "./navigation";
import { Integrations } from "./integrations";
import { AgentTestChat } from "@/features/create-agent/agent-test-chat";
import { ReadinessPanel } from "./readiness-panel";
import { DashboardHelp } from "./dashboard-help";
import { KnowledgeBase } from "./knowledge-base";
import { AgentSettings } from "./agent-settings";
import { useWizardStorage } from "@/features/create-agent/use-wizard-storage";
import { dashboardDestination, dashboardGroups as groups, type DashboardView } from "./navigation";
import type { IntegrationsResponse, Session } from "@/lib/api/types";

const pages = groups.flatMap(group => [...group.items]);
const controlClass = "flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-md border-0 bg-transparent p-1 text-plumo-muted transition-colors hover:bg-plumo-line/65 hover:text-plumo-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue";

export function DashboardShell({ session, conversation = null }: { session: Session; conversation?: string | null }) {
  const { locale, t } = useLanguage();
  const [collapsed, setCollapsed] = useState(false);
  const [inboxView, setInboxView] = useState<"list" | "kanban">("list");
  useEffect(() => {
    try {
      if (!dashboardConversation(window.location.search) && window.localStorage.getItem("plumo-inbox-view") === "kanban") setInboxView("kanban");
    } catch { /* A blocked preference store must not block the inbox. */ }
    const openLinkedConversation = () => { if (dashboardConversation(window.location.search)) setInboxView("list"); };
    window.addEventListener("popstate", openLinkedConversation);
    return () => window.removeEventListener("popstate", openLinkedConversation);
  }, []);
  function selectInboxView(next: "list" | "kanban") {
    if (next === "kanban") {
      const url = new URL(window.location.href);
      url.searchParams.delete("conversation");
      window.history.replaceState(null, "", url.pathname + url.search + "#chats");
    }
    setInboxView(next);
    try { window.localStorage.setItem("plumo-inbox-view", next); } catch { /* Optional preference. */ }
  }
  const setup = useWizardStorage("account");
  const [materialEditing, setMaterialEditing] = useState(false);
  const [publishedBusinessName, setPublishedBusinessName] = useState(session.operator.business.name);
  useEffect(() => {
    if (setup.completed) setPublishedBusinessName(setup.snapshot.settings.company.trim() || session.operator.business.name);
  }, [setup.completed, setup.snapshot.settings.company, session.operator.business.name]);
  const [view, setView] = useState<DashboardView>("chats");
  const [integrations, setIntegrations] = useState<IntegrationsResponse | null>(null);
  const [integrationStatus, setIntegrationStatus] = useState<"loading" | "ready" | "error">("loading");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [leaving, setLeaving] = useState(false);
  const [logoutError, setLogoutError] = useState(false);
  const c = locale === "ru" ? {
    menu: "Навигация", collapse: "Свернуть панель", expand: "Развернуть панель",
    disabled: "Ответы ИИ отключены", description: "Продолжайте обучать и тестировать ИИ-агента. Включите ответы клиентам, когда будете готовы.",
    enable: "Настроить ИИ", enabled: "Ответы ИИ включены", checking: "Проверяем состояние ИИ…", activeChannels: "Активные каналы", logout: "Выйти", logoutFailed: "Не удалось выйти. Повторите попытку.", mock: "Модель: mock", period: "Период", kanban: "Канбан", list: "Список", more: "Ещё",
    trial: "Сопровождаемый пилот", subscription: "Условия и помощь", help: "Помощь", statusError: "Не удалось проверить состояние ИИ", statusHint: "Проверьте подключение и повторите запрос.", retry: "Повторить",
  } : {
    menu: "Navigation", collapse: "Collapse sidebar", expand: "Expand sidebar",
    disabled: "AI replies are disabled", description: "Keep training and testing your AI agent. Enable customer replies when you are ready.",
    enable: "Manage AI", enabled: "AI replies are enabled", checking: "Checking AI status…", activeChannels: "Active channels", logout: "Sign out", logoutFailed: "Could not sign out. Please try again.", mock: "Model: mock", period: "Date range", kanban: "Kanban", list: "List", more: "More options",
    trial: "Supported pilot", subscription: "Pilot terms and help", help: "Help", statusError: "Could not check AI status", statusHint: "Check your connection and retry.", retry: "Retry",
  };
  const title = view === "help" ? c.help : pages.find(page => page.id === view)?.[locale];
  const activeChannels = (integrations?.channels ?? [])
    .filter(item => item.connection?.status === "connected" && item.connection.agent_enabled)
    .map(item => item.channel === "telegram" ? "Telegram" : "Instagram");
  const operator = session.operator.display_name || session.operator.email;
  const business = publishedBusinessName;

  async function logout() {
    setLeaving(true);
    setLogoutError(false);
    try {
      const response = await fetch("/api/auth/logout", { method: "POST", headers: { "x-plumo-request": "1" }, credentials: "same-origin" });
      if (!response.ok) throw new Error("logout_failed");
      window.location.assign("/login");
    } catch {
      setLogoutError(true);
      setLeaving(false);
    }
  }

  function openInbox() {
    navigate("chats");
  }

  useEffect(() => {
    const readHash = () => {
      const destination = dashboardDestination(window.location.hash);
      if (destination) setView(destination);
    };
    readHash();
    window.addEventListener("hashchange", readHash);
    return () => window.removeEventListener("hashchange", readHash);
  }, []);

  function navigate(next: DashboardView) {
    setView(next);
    window.location.hash = next;
  }

  function navigation(mobile = false) {
    const compact = collapsed && !mobile;
    return groups.map(group => <div key={group.en} className="mb-2">
      <p title={compact ? group[locale] : undefined} className={`m-0 flex h-6 items-center px-1 text-[10.5px] text-plumo-muted ${compact ? "justify-center" : ""}`}>
        {compact ? <span aria-label={group[locale]}>···</span> : group[locale]}
      </p>
      {group.items.map(item => <a key={item.id} href={item.href} aria-current={view === item.id ? "page" : undefined} aria-label={item[locale]} title={compact ? item[locale] : undefined} onClick={event => {
        event.currentTarget.closest("details")?.removeAttribute("open");
      }} className={`flex h-7 w-full cursor-pointer items-center gap-1.5 rounded-[4px] border-0 px-3 text-left font-[inherit] text-[11.5px] text-plumo-ink no-underline transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-plumo-blue ${view === item.id ? "bg-plumo-ink/[0.065]" : "bg-transparent hover:bg-plumo-ink/[0.04]"} ${compact ? "justify-center px-0" : ""}`}>
        <span className="flex shrink-0 text-plumo-ink/75"><DashboardIcon name={item.icon} size={16} /></span>{!compact && <span className="truncate">{item[locale]}</span>}
      </a>)}
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
          <a href="#help" className="flex min-h-[30px] items-center justify-center gap-1 rounded-[4px] border border-solid border-plumo-blue/25 bg-plumo-soft px-1 text-center text-[11px] text-plumo-ink no-underline hover:bg-plumo-blue/10 focus-visible:outline-2 focus-visible:outline-plumo-blue">{c.subscription}<DashboardIcon name="sparkles" size={14} /></a>
        </>}
        <a href="#help" aria-current={view === "help" ? "page" : undefined} aria-label={c.help} title={collapsed ? c.help : undefined} className={`flex h-7 items-center gap-1.5 rounded-md px-3 text-[11.5px] text-plumo-ink no-underline hover:bg-plumo-ink/[0.04] focus-visible:outline-2 focus-visible:outline-plumo-blue ${collapsed ? "justify-center px-0" : ""}`}><DashboardIcon name="help" size={16} />{!collapsed && c.help}</a>
        <div className="mt-2 border-0 border-t border-solid border-plumo-ink/10 pt-1">
          {!collapsed && <div className="px-3 py-1.5" title={`${business} · ${operator}`}><p className="m-0 truncate text-[10.5px] font-medium">{business}</p><p className="mb-0 mt-0.5 truncate text-[10px] text-plumo-muted">{operator}</p></div>}
          <button type="button" onClick={logout} disabled={leaving} aria-label={c.logout} title={collapsed ? c.logout : undefined} className={`flex h-7 w-full cursor-pointer items-center gap-1.5 rounded-md border-0 bg-transparent px-3 text-left text-[11.5px] text-plumo-ink hover:bg-plumo-ink/[0.04] disabled:opacity-50 ${collapsed ? "justify-center px-0" : ""}`}><DashboardIcon name="logout" size={16} />{!collapsed && c.logout}</button>
        </div>
        {!collapsed && <div className="mt-2 px-1 [&_button]:min-h-7 [&_button]:px-1.5 [&_button]:py-1 [&_button]:text-[9px]"><LanguageSwitch /></div>}
      </div>
    </aside>
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-[3px] bg-white">
      <header className="flex min-h-14 shrink-0 items-center gap-3 border-0 border-b border-solid border-plumo-line px-3 py-2.5 md:pl-[15px]">
        <span className="hidden text-plumo-muted sm:flex"><DashboardIcon name={integrationStatus === "ready" && activeChannels.length ? "sparkles" : "pause"} size={13} /></span>
        <div className="min-w-0 flex-1" role="status"><p className="m-0 text-xs font-semibold leading-[18px]">{integrationStatus === "error" ? c.statusError : integrationStatus === "loading" ? c.checking : activeChannels.length ? c.enabled : c.disabled}</p><p className="m-0 hidden text-xs leading-[18px] text-plumo-muted sm:block">{integrationStatus === "error" ? c.statusHint : integrationStatus === "ready" && activeChannels.length ? `${c.activeChannels}: ${activeChannels.join(", ")}` : c.description}</p></div>
        {integrationStatus === "error" && <button type="button" onClick={() => { setIntegrationStatus("loading"); setRefreshVersion(value => value + 1); }} className="min-h-9 cursor-pointer rounded-lg border border-solid border-plumo-line bg-white px-2 text-xs text-plumo-blue focus-visible:outline-2 focus-visible:outline-plumo-blue">{c.retry}</button>}
        <button type="button" onClick={() => navigate("integrations")} className="min-h-[25px] shrink-0 cursor-pointer rounded-lg border border-solid border-plumo-ink/80 bg-plumo-ink px-2 py-1 font-[inherit] text-[11px] text-white shadow-sm hover:bg-plumo-ink/85 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue">{c.enable}</button>
      </header>
      {logoutError && <p role="alert" className="m-0 border-0 border-b border-solid border-plumo-line bg-plumo-soft px-4 py-2 text-xs">{c.logoutFailed}</p>}
      <main id="workspace" tabIndex={-1} aria-label={title} className="flex min-h-0 flex-1 flex-col bg-plumo-line/15 focus:outline-none">
        <div className="flex min-h-10 shrink-0 flex-wrap items-center gap-2 border-0 border-b border-solid border-plumo-line px-2.5 py-1 md:pl-3.5">
          <details className="relative z-20 md:hidden" onKeyDown={event => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
            <summary aria-label={c.menu} className={`${controlClass} list-none [&::-webkit-details-marker]:hidden`}><DashboardIcon name="menu" size={18} /></summary>
            <nav aria-label={c.menu} className="absolute left-0 top-9 max-h-[calc(100dvh-130px)] w-52 overflow-y-auto rounded-lg border border-solid border-plumo-line bg-white p-2 shadow-xl">
              {navigation(true)}
              <a href="#help" onClick={event => event.currentTarget.closest("details")?.removeAttribute("open")} className="flex min-h-9 items-center px-3 text-xs text-plumo-blue">{c.help}</a>
              <div className="border-0 border-t border-solid border-plumo-line pt-1">
                <p className="mx-3 my-1 truncate text-[11px]" title={operator}>{business} · {operator}</p>
                <button type="button" onClick={logout} disabled={leaving} className="flex h-8 w-full cursor-pointer items-center gap-2 rounded-md border-0 bg-transparent px-3 text-xs text-plumo-muted hover:bg-plumo-line/40 disabled:opacity-50"><DashboardIcon name="logout" size={16} />{c.logout}</button>
                <LanguageSwitch />
              </div>
            </nav>
          </details>
          <h1 className="m-0 text-xs font-normal text-plumo-muted">{title}</h1>
          {session.ai_mode === "mock" && <span className="rounded bg-plumo-soft px-1.5 py-0.5 text-[9px] text-plumo-muted">{c.mock}</span>}

        </div>
        <div className={view === "integrations" ? "min-h-0 flex-1" : "hidden"}><Integrations onDialogues={openInbox} onStateChange={setIntegrations} onLoadStateChange={setIntegrationStatus} refreshVersion={refreshVersion} /></div>
        <div className={view === "chats" ? "flex min-h-0 flex-1 flex-col" : "hidden"}>
          {view === "chats" && <ReadinessPanel onTesting={() => navigate("testing")} onIntegrations={() => navigate("integrations")} />}
          <div className="flex shrink-0 justify-end gap-1 border-0 border-b border-solid border-plumo-line bg-white px-4 py-2" role="group" aria-label={locale === "ru" ? "Вид диалогов" : "Conversation view"}>{(["list", "kanban"] as const).map(value => <button key={value} type="button" aria-pressed={inboxView === value} onClick={() => selectInboxView(value)} className={`cursor-pointer rounded-lg border border-solid border-plumo-line px-3 py-1.5 font-[inherit] text-xs focus-visible:outline-2 focus-visible:outline-plumo-blue ${inboxView === value ? "bg-plumo-soft text-plumo-blue" : "bg-white text-plumo-muted"}`}>{value === "list" ? c.list : c.kanban}</button>)}</div>
          <div className={inboxView === "list" ? "min-h-0 flex-1" : "hidden"}><Dialogues active={view === "chats" && inboxView === "list"} /></div>
          {inboxView === "kanban" && view === "chats" && <div className="min-h-0 flex-1"><Kanban onOpen={id => { window.history.pushState(null, "", conversationHref(id)); selectInboxView("list"); }} /></div>}
        </div>
        <div className={view === "improvements" ? "min-h-0 flex-1" : "hidden"}><Improvements active={view === "improvements"} /></div>
        {view === "statistics" && <div className="min-h-0 flex-1"><Statistics active /></div>}
        {view === "customers" && <div className="min-h-0 flex-1"><Customers active /></div>}
        {view === "testing" && <div className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6"><div className="mx-auto max-w-[900px]"><AgentTestChat /></div></div>}
        {view === "help" && <DashboardHelp />}
        <div className={view === "knowledge" ? "min-h-0 flex-1" : "hidden"}><KnowledgeBase active={view === "knowledge"} storage={setup} onEditingChange={setMaterialEditing} /></div>
        <div className={view === "settings" ? "min-h-0 flex-1" : "hidden"}><AgentSettings active={view === "settings"} storage={setup} materialEditing={materialEditing} /></div>
        <div className={view === "scenarios" ? "min-h-0 flex-1" : "hidden"}><AgentSettings scenario active={view === "scenarios"} storage={setup} materialEditing={materialEditing} /></div>
      </main>
    </div>
  </div>;
}
