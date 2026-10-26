"use client";

import { useEffect, useRef } from "react";
import { useLanguage } from "@/lib/i18n";
import { DashboardIcon } from "./dashboard-icon";

export function SoonDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const { locale } = useLanguage();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (open && !dialog?.open) dialog?.showModal();
    if (!open && dialog?.open) dialog.close();
  }, [open]);

  return <dialog ref={dialogRef} aria-labelledby="dashboard-soon-title" onClose={onClose}
    onClick={event => {
      if (event.target !== event.currentTarget) return;
      const box = event.currentTarget.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) event.currentTarget.close();
    }}
    className="fixed w-[320px] max-w-[calc(100vw-32px)] rounded-xl border border-solid border-plumo-line bg-white px-6 py-14 text-plumo-muted shadow-xl backdrop:bg-plumo-ink/20 backdrop:backdrop-blur-[2px]">
    <button type="button" aria-label={locale === "ru" ? "Закрыть" : "Close"} onClick={() => dialogRef.current?.close()} className="absolute right-2 top-2 flex size-8 cursor-pointer items-center justify-center rounded-md border-0 bg-transparent text-plumo-muted hover:bg-plumo-line/40 focus-visible:outline-2 focus-visible:outline-plumo-blue"><DashboardIcon name="close" size={16} /></button>
    <h2 id="dashboard-soon-title" className="m-0 text-center text-xl font-normal">soon</h2>
  </dialog>;
}
