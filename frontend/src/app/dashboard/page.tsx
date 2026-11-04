import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { DashboardShell } from "@/features/dashboard/dashboard-shell";
import { currentSession } from "@/lib/server/backend";
import { conversationHref, customerHref, knowledgeHref, improvementHref, testingHref } from "@/features/dashboard/navigation";

export const metadata: Metadata = {
  title: "Кабинет — Plumo",
  robots: { index: false, follow: false },
};

// Real customer messages: the page is rendered only for a session the backend accepts.
export const dynamic = "force-dynamic";

export default async function DashboardPage({ searchParams }: { searchParams: Promise<{ conversation?: string | string[]; source?: string | string[]; customer?: string | string[]; issue?: string | string[]; test?: string | string[] }> }) {
  const check = await currentSession();
  if (check.state === "anonymous") {
    const query = await searchParams;
    const next = typeof query.issue === "string" ? improvementHref(query.issue) : typeof query.test === "string" ? testingHref(query.test) : typeof query.customer === "string" ? customerHref(query.customer) : typeof query.source === "string" ? knowledgeHref(query.source) : typeof query.conversation === "string" ? conversationHref(query.conversation) : "/dashboard";
    redirect(`/login?next=${encodeURIComponent(next)}`);
  }
  if (check.state === "unavailable") {
    return <main className="flex min-h-svh items-center justify-center bg-plumo-line/15 px-4 text-plumo-ink">
      <div className="max-w-md rounded-2xl border border-solid border-plumo-line bg-white p-8 text-center">
        <h1 className="m-0 text-xl font-semibold">Сервер Plumo недоступен</h1>
        <p className="mb-0 mt-3 text-sm leading-6 text-plumo-muted">Не удалось проверить вход. Убедитесь, что API запущен (PLUMO_API_URL), и обновите страницу.</p>
        <Link href="/dashboard" className="mt-6 inline-flex rounded-lg bg-plumo-blue px-4 py-2.5 text-sm font-medium text-white">Обновить</Link>
      </div>
    </main>;
  }
  return <DashboardShell session={check.session} />;
}
