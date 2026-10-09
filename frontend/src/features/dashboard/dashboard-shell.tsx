"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { LanguageSwitch, useLanguage } from "@/lib/i18n";
import { DashboardIcon } from "./dashboard-icon";
import { Dialogues } from "./dialogues";
import { Integrations } from "./integrations";

export function DashboardShell() {
  const { locale, t } = useLanguage();
  const [collapsed, setCollapsed] = useState(false);
  const [view, setView] = useState<"integrations" | "dialogues">("integrations");
  const c = locale === "ru" ? {
    menu: "Навигация", collapse: "Свернуть панель", expand: "Развернуть панель",
    back: "На сайт", dialogues: "Диалоги", integrations: "Интеграции", workspace: "Рабочее пространство", business: "Пример бизнеса",
  } : {
    menu: "Navigation", collapse: "Collapse sidebar", expand: "Expand sidebar",
    back: "Back to website", dialogues: "Conversations", integrations: "Integrations", workspace: "Workspace", business: "Example business",
  };
  const controlClass = "flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-plumo-muted transition-colors hover:bg-plumo-line/60 hover:text-plumo-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue";
  function navigation(mobile = false) {
    return (["integrations", "dialogues"] as const).map(item => <button key={item} type="button" aria-current={view === item ? "page" : undefined} aria-label={c[item]} title={!mobile && collapsed ? c[item] : undefined} onClick={() => setView(item)} className={`mb-1 flex min-h-10 w-full cursor-pointer items-center gap-3 rounded-lg border-0 px-3 py-2.5 text-left font-[inherit] text-[13px] font-medium focus-visible:outline-2 focus-visible:outline-plumo-blue ${view === item ? "bg-plumo-soft text-plumo-blue" : "bg-transparent text-plumo-muted hover:bg-plumo-line/40"} ${!mobile && collapsed ? "justify-center" : ""}`}><DashboardIcon name={item === "integrations" ? "plug" : "chat"} size={18} />{(mobile || !collapsed) && c[item]}</button>);
  }

  return <div className="flex h-svh overflow-hidden bg-white text-plumo-ink">
    <a href="#workspace" className="skip-link">{t.skip}</a>
    <aside aria-label={c.menu} className={`hidden h-full shrink-0 flex-col border-0 border-r border-solid border-plumo-line bg-plumo-line/20 transition-[width] duration-200 md:flex ${collapsed ? "w-[72px]" : "w-[216px]"}`}>
      <div className={`flex h-16 shrink-0 items-center ${collapsed ? "justify-center" : "justify-between pl-5 pr-3"}`}>
        {!collapsed && <Link href="/" aria-label={t.home} className="relative block h-8 w-[110px] overflow-hidden rounded-sm"><Image src="/images/plumo-logo.png" alt="" width={110} height={110} priority className="absolute -top-[41px] left-0 mix-blend-multiply" /></Link>}
        <button type="button" className={controlClass} aria-label={collapsed ? c.expand : c.collapse} title={collapsed ? c.expand : c.collapse} aria-expanded={!collapsed} aria-controls="dashboard-nav" onClick={() => setCollapsed(value => !value)}><DashboardIcon name="panel" size={18} /></button>
      </div>
      <div className={`mx-3 mb-6 flex min-h-12 items-center gap-2.5 rounded-xl border border-solid border-plumo-line bg-white ${collapsed ? "justify-center" : "px-3"}`} title={collapsed ? c.business : undefined}>
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-plumo-ink text-[11px] font-semibold text-white">P</span>
        {!collapsed && <div className="min-w-0"><p className="m-0 truncate text-xs font-medium">Plumo</p><p className="mb-0 mt-0.5 text-[10px] text-plumo-muted">{c.business}</p></div>}
      </div>
      <nav id="dashboard-nav" className="flex-1 px-3">
        {navigation()}
      </nav>
      <div className="border-0 border-t border-solid border-plumo-line p-3"><Link href="/" aria-label={c.back} title={collapsed ? c.back : undefined} className={`flex min-h-10 items-center gap-3 rounded-lg px-3 text-xs text-plumo-muted transition-colors hover:bg-plumo-soft hover:text-plumo-blue ${collapsed ? "justify-center" : ""}`}><DashboardIcon name="back" size={18} />{!collapsed && c.back}</Link></div>
    </aside>
    <div className="flex min-w-0 flex-1 flex-col">
      <header className="flex h-16 shrink-0 items-center justify-between gap-2 border-0 border-b border-solid border-plumo-line px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <details className="relative z-20 md:hidden" onKeyDown={event => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
            <summary aria-label={c.menu} className={`${controlClass} list-none [&::-webkit-details-marker]:hidden`}><DashboardIcon name="menu" /></summary>
            <nav className="absolute left-0 top-12 w-52 rounded-xl border border-solid border-plumo-line bg-white p-2 shadow-lg" onClick={event => event.currentTarget.closest("details")?.removeAttribute("open")}>
              {navigation(true)}
              <Link href="/" className="mt-1 flex items-center gap-3 rounded-lg px-3 py-3 text-sm text-plumo-muted hover:bg-plumo-line/30"><DashboardIcon name="back" size={18} />{c.back}</Link>
            </nav>
          </details>
          <Link href="/" className="relative block h-8 w-[100px] overflow-hidden md:hidden" aria-label={t.home}><Image src="/images/plumo-logo.png" alt="" width={100} height={100} priority className="absolute -top-[38px] left-0" /></Link>
          <span className="hidden text-xs text-plumo-muted md:block">{c.workspace}<span className="mx-3 text-plumo-line">/</span><span className="text-plumo-ink">{c[view]}</span></span>
        </div>
        <LanguageSwitch />
      </header>
      <main id="workspace" tabIndex={-1} aria-label={c[view]} className="min-h-0 flex-1 focus:outline-none">
        <div className={view === "integrations" ? "h-full" : "hidden"}><Integrations onDialogues={() => setView("dialogues")} /></div>
        <div className={view === "dialogues" ? "h-full" : "hidden"}><Dialogues /></div>
      </main>
    </div>
  </div>;
}
