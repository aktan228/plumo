"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { LanguageSwitch, useLanguage } from "@/lib/i18n";

const copy = {
  ru: {
    title: "Рабочее пространство", preview: "Предпросмотр", menu: "Боковая панель",
    collapse: "Свернуть панель", expand: "Развернуть панель", back: "На сайт",
    empty: "Здесь будет ваш кабинет", description: "Разделы будем добавлять постепенно.",
  },
  en: {
    title: "Workspace", preview: "Preview", menu: "Sidebar",
    collapse: "Collapse sidebar", expand: "Expand sidebar", back: "Back to website",
    empty: "Your workspace starts here", description: "Sections will be added step by step.",
  },
};

function PanelIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="3" y="4" width="18" height="16" rx="3" /><path d="M9 4v16" />
  </svg>;
}

export function DashboardShell() {
  const { locale, t } = useLanguage();
  const c = copy[locale];
  const [collapsed, setCollapsed] = useState(false);
  const controlClass = "flex size-10 shrink-0 cursor-pointer items-center justify-center rounded-xl border-0 bg-transparent text-plumo-muted transition-colors hover:bg-plumo-line/60 hover:text-plumo-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plumo-blue";

  return <div className="flex min-h-svh bg-plumo-line/25 text-plumo-ink">
    <a href="#workspace" className="skip-link">{t.skip}</a>
    <aside aria-label={c.menu} className={`sticky top-0 hidden h-svh shrink-0 flex-col border-0 border-r border-solid border-plumo-line bg-white transition-[width] duration-200 md:flex ${collapsed ? "w-[76px]" : "w-[248px]"}`}>
      <div className={`flex h-[76px] shrink-0 items-center ${collapsed ? "justify-center" : "justify-between pl-6 pr-3"}`}>
        {!collapsed && <Link href="/" aria-label={t.home} className="relative block h-8 w-[120px] overflow-hidden rounded-sm">
          <Image src="/images/plumo-logo.png" alt="" width={120} height={120} priority className="absolute -top-[45px] left-0" />
        </Link>}
        <button type="button" className={controlClass} aria-label={collapsed ? c.expand : c.collapse} title={collapsed ? c.expand : c.collapse} aria-expanded={!collapsed} aria-controls="dashboard-sidebar-body" onClick={() => setCollapsed(value => !value)}><PanelIcon /></button>
      </div>
      <div id="dashboard-sidebar-body" className="flex-1" />
      <div className="border-0 border-t border-solid border-plumo-line p-3">
        <Link href="/" aria-label={c.back} title={collapsed ? c.back : undefined} className={`flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm text-plumo-muted transition-colors hover:bg-plumo-soft hover:text-plumo-blue ${collapsed ? "justify-center" : ""}`}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M19 12H5m6-6-6 6 6 6" /></svg>
          {!collapsed && c.back}
        </Link>
      </div>
    </aside>
    <div className="flex min-w-0 flex-1 flex-col">
      <header className="flex min-h-[76px] flex-wrap items-center justify-between gap-3 border-0 border-b border-solid border-plumo-line bg-white px-5 py-3 sm:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <Link href="/" className="relative block h-8 w-[100px] overflow-hidden md:hidden" aria-label={t.home}><Image src="/images/plumo-logo.png" alt="" width={100} height={100} priority className="absolute -top-[38px] left-0" /></Link>
          <h1 className="m-0 hidden text-[15px] font-medium sm:block">{c.title}</h1>
          <span className="rounded-md bg-plumo-soft px-2.5 py-1 text-xs font-medium text-plumo-blue">{c.preview}</span>
        </div>
        <LanguageSwitch />
      </header>
      <main id="workspace" tabIndex={-1} aria-label={c.title} className="flex flex-1 p-3 focus:outline-none sm:p-6">
        <div className="flex min-h-[calc(100svh-124px)] w-full items-center justify-center rounded-2xl border border-solid border-plumo-line bg-white px-6 py-12">
          <div className="max-w-sm text-center">
            <div className="mx-auto mb-5 flex size-12 items-center justify-center rounded-2xl bg-plumo-soft text-plumo-blue"><PanelIcon /></div>
            <h2 className="m-0 text-xl font-medium tracking-tight">{c.empty}</h2>
            <p className="mb-0 mt-2 text-sm leading-6 text-plumo-muted">{c.description}</p>
          </div>
        </div>
      </main>
    </div>
  </div>;
}
