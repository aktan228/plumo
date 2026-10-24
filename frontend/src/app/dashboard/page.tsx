import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { DashboardShell } from "@/features/dashboard/dashboard-shell";
import { currentSession } from "@/lib/server/backend";

export const metadata: Metadata = {
  title: "Кабинет — Plumo",
  robots: { index: false, follow: false },
};

// Real customer messages: the page is rendered only for a session the backend accepts.
export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const check = await currentSession();
  if (check.state === "anonymous") redirect("/login?next=/dashboard");
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
