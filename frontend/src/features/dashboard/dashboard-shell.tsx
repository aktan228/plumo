"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import ArrowLeft01Icon from "@hugeicons/core-free-icons/ArrowLeft01Icon";
import Chatting01Icon from "@hugeicons/core-free-icons/Chatting01Icon";
import Logout01Icon from "@hugeicons/core-free-icons/Logout01Icon";
import Menu01Icon from "@hugeicons/core-free-icons/Menu01Icon";
import Plug01Icon from "@hugeicons/core-free-icons/Plug01Icon";
import SidebarLeftIcon from "@hugeicons/core-free-icons/SidebarLeftIcon";
import { PlumoIcon } from "@/components/ui/plumo-icon";
import type { Session } from "@/lib/api/types";
import { LanguageSwitch, useLanguage } from "@/lib/i18n";
import { Dialogues } from "./dialogues";
import { Integrations } from "./integrations";

export function DashboardShell({ session }: { session: Session }) {
  const { locale, t } = useLanguage();
  const [collapsed, setCollapsed] = useState(false);
  const [view, setView] = useState<"integrations" | "dialogues">("integrations");
  const [leaving, setLeaving] = useState(false);
  const business = session.operator.business.name;
  const operator = session.operator.display_name || session.operator.email;
  const c = locale === "ru" ? {
    menu: "Навигация", collapse: "Свернуть панель", expand: "Развернуть панель",
    back: "На сайт", dialogues: "Диалоги", integrations: "Интеграции", workspace: "Рабочее пространство", logout: "Выйти", mock: "Модель: mock",
  } : {
    menu: "Navigation", collapse: "Collapse sidebar", expand: "Expand sidebar",
    back: "Back to website", dialogues: "Conversations", integrations: "Integrations", workspace: "Workspace", logout: "Sign out", mock: "Model: mock",
  };
  const controlClass = "flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-plumo-muted transition-colors hover:bg-plumo-line/60 hover:text-plumo-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue";

  async function logout() {
    setLeaving(true);
    await fetch("/api/auth/logout", { method: "POST", headers: { "x-plumo-request": "1" }, credentials: "same-origin" }).catch(() => null);
    window.location.assign("/login");
  }

  function navigation(mobile = false) {
    return (["integrations", "dialogues"] as const).map(item => <button key={item} type="button" aria-current={view === item ? "page" : undefined} aria-label={c[item]} title={!mobile && collapsed ? c[item] : undefined} onClick={() => setView(item)} className={`mb-1 flex min-h-10 w-full cursor-pointer items-center gap-3 rounded-lg border-0 px-3 py-2.5 text-left font-[inherit] text-[13px] font-medium focus-visible:outline-2 focus-visible:outline-plumo-blue ${view === item ? "bg-plumo-soft text-plumo-blue" : "bg-transparent text-plumo-muted hover:bg-plumo-line/40"} ${!mobile && collapsed ? "justify-center" : ""}`}><PlumoIcon icon={item === "integrations" ? Plug01Icon : Chatting01Icon} size={18} />{(mobile || !collapsed) && c[item]}</button>);
  }

  return <div className="flex h-svh overflow-hidden bg-white text-plumo-ink">
    <a href="#workspace" className="skip-link">{t.skip}</a>
    <aside aria-label={c.menu} className={`hidden h-full shrink-0 flex-col border-0 border-r border-solid border-plumo-line bg-plumo-line/20 transition-[width] duration-200 md:flex ${collapsed ? "w-[72px]" : "w-[216px]"}`}>
      <div className={`flex h-16 shrink-0 items-center ${collapsed ? "justify-center" : "justify-between pl-5 pr-3"}`}>
        {!collapsed && <Link href="/" aria-label={t.home} className="relative block h-8 w-[110px] overflow-hidden rounded-sm"><Image src="/images/plumo-logo.png" alt="" width={110} height={110} priority className="absolute -top-[41px] left-0 mix-blend-multiply" /></Link>}
        <button type="button" className={controlClass} aria-label={collapsed ? c.expand : c.collapse} title={collapsed ? c.expand : c.collapse} aria-expanded={!collapsed} aria-controls="dashboard-nav" onClick={() => setCollapsed(value => !value)}><PlumoIcon icon={SidebarLeftIcon} size={18} /></button>
      </div>
      <div className={`mx-3 mb-6 flex min-h-12 items-center gap-2.5 rounded-xl border border-solid border-plumo-line bg-white ${collapsed ? "justify-center" : "px-3"}`} title={collapsed ? business : undefined}>
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-plumo-ink text-[11px] font-semibold text-white">{business.slice(0, 1).toLocaleUpperCase()}</span>
        {!collapsed && <div className="min-w-0"><p className="m-0 truncate text-xs font-medium">{business}</p><p className="mb-0 mt-0.5 truncate text-[10px] text-plumo-muted">{operator}</p></div>}
      </div>
      <nav id="dashboard-nav" className="flex-1 px-3">
        {navigation()}
      </nav>
      <div className="space-y-1 border-0 border-t border-solid border-plumo-line p-3">
        <button type="button" disabled={leaving} onClick={logout} aria-label={c.logout} title={collapsed ? c.logout : undefined} className={`flex min-h-10 w-full cursor-pointer items-center gap-3 rounded-lg border-0 bg-transparent px-3 font-[inherit] text-xs text-plumo-muted transition-colors hover:bg-plumo-soft hover:text-plumo-blue disabled:opacity-60 ${collapsed ? "justify-center" : ""}`}><PlumoIcon icon={Logout01Icon} size={18} />{!collapsed && c.logout}</button>
        <Link href="/" aria-label={c.back} title={collapsed ? c.back : undefined} className={`flex min-h-10 items-center gap-3 rounded-lg px-3 text-xs text-plumo-muted transition-colors hover:bg-plumo-soft hover:text-plumo-blue ${collapsed ? "justify-center" : ""}`}><PlumoIcon icon={ArrowLeft01Icon} size={18} />{!collapsed && c.back}</Link>
      </div>
    </aside>
    <div className="flex min-w-0 flex-1 flex-col">
      <header className="flex h-16 shrink-0 items-center justify-between gap-2 border-0 border-b border-solid border-plumo-line px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <details className="relative z-20 md:hidden" onKeyDown={event => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
            <summary aria-label={c.menu} className={`${controlClass} list-none [&::-webkit-details-marker]:hidden`}><PlumoIcon icon={Menu01Icon} /></summary>
            <nav className="absolute left-0 top-12 w-52 rounded-xl border border-solid border-plumo-line bg-white p-2 shadow-lg" onClick={event => event.currentTarget.closest("details")?.removeAttribute("open")}>
              <p className="mx-3 mb-2 mt-1 truncate text-xs font-medium">{business}</p>
              {navigation(true)}
              <button type="button" onClick={logout} className="mt-1 flex w-full cursor-pointer items-center gap-3 rounded-lg border-0 bg-transparent px-3 py-3 text-left font-[inherit] text-sm text-plumo-muted hover:bg-plumo-line/30"><PlumoIcon icon={Logout01Icon} size={18} />{c.logout}</button>
              <Link href="/" className="mt-1 flex items-center gap-3 rounded-lg px-3 py-3 text-sm text-plumo-muted hover:bg-plumo-line/30"><PlumoIcon icon={ArrowLeft01Icon} size={18} />{c.back}</Link>
            </nav>
          </details>
          <Link href="/" className="relative block h-8 w-[100px] overflow-hidden md:hidden" aria-label={t.home}><Image src="/images/plumo-logo.png" alt="" width={100} height={100} priority className="absolute -top-[38px] left-0" /></Link>
          <span className="hidden text-xs text-plumo-muted md:block">{c.workspace}<span className="mx-3 text-plumo-line">/</span><span className="text-plumo-ink">{c[view]}</span></span>
        </div>
        <div className="flex items-center gap-3">
          {session.ai_mode === "mock" && <span className="hidden rounded-md bg-amber-50 px-2 py-1 text-[11px] text-amber-800 sm:inline">{c.mock}</span>}
          <LanguageSwitch />
        </div>
      </header>
      <main id="workspace" tabIndex={-1} aria-label={c[view]} className="min-h-0 flex-1 focus:outline-none">
        <div className={view === "integrations" ? "h-full" : "hidden"}><Integrations onDialogues={() => setView("dialogues")} /></div>
        <div className={view === "dialogues" ? "h-full" : "hidden"}><Dialogues active={view === "dialogues"} /></div>
      </main>
    </div>
  </div>;
}
