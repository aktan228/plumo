import type { Metadata } from "next";
import { DashboardShell } from "@/features/dashboard/dashboard-shell";

export const metadata: Metadata = {
  title: "Кабинет — Plumo",
  robots: { index: false, follow: false },
};

export default function DashboardPage() {
  return <DashboardShell />;
}
