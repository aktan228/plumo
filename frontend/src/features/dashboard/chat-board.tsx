"use client";

import { useLanguage } from "@/lib/i18n";
import { DashboardIcon } from "./dashboard-icon";

export function ChatBoard({ onSoon }: { onSoon: () => void }) {
  const { locale } = useLanguage();
  const stages = locale === "ru"
    ? ["Без статуса", "Новый лид", "Выявление потребности", "Квалифицирован", "Встреча назначена"]
    : ["No status", "New Lead", "In Discovery", "Qualified Lead", "Consultation Booked"];

  return <section aria-label={locale === "ru" ? "Канбан диалогов" : "Chats kanban board"} tabIndex={0} className="flex h-full min-h-0 gap-[26px] overflow-x-auto px-2.5 pb-3 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-plumo-blue [scrollbar-color:var(--muted)_transparent] [scrollbar-width:thin]">
    {stages.map((stage, index) => <section key={index} aria-label={stage} className="w-[215px] shrink-0">
      <h2 className="m-0 text-xs font-normal">
        <button type="button" onClick={onSoon} className="flex h-9 w-full cursor-pointer items-center gap-[7px] border-0 bg-transparent p-0 text-left font-[inherit] text-plumo-ink focus-visible:outline-2 focus-visible:outline-plumo-blue">
          <span aria-hidden="true" className={`size-[7px] shrink-0 rounded-full ${index === 0 ? "bg-plumo-muted/65" : "bg-plumo-muted"}`} />
          <span className="truncate">{stage}</span>
          {index > 0 && <span className="text-plumo-line"><DashboardIcon name="info" size={10} /></span>}
          <span className="ml-auto text-[10px] text-plumo-muted/70">0</span>
          <span className="ml-3 text-plumo-line"><DashboardIcon name="drag" size={10} /></span>
        </button>
      </h2>
      <div className="flex h-[69px] items-center justify-center rounded-[9px] border border-dashed border-plumo-line/65 text-[10px] text-plumo-muted">
        {locale === "ru" ? "Пока нет лидов" : "No leads yet"}
      </div>
    </section>)}
  </section>;
}
