import type { Metadata } from "next";
import { currentSession } from "@/lib/server/backend";
import { CreateAgentWizard } from "@/features/create-agent/create-agent-wizard";

export const metadata: Metadata = { title: "Создать демо агента — Plumo" };

export default async function CreateWizardPage() {
  const check = await currentSession();
  return <CreateAgentWizard mode={check.state === "ok" ? "account" : check.state === "anonymous" ? "guest" : "unavailable"} />;
}
