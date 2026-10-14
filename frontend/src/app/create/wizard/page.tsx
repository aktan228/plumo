import type { Metadata } from "next";
import { CreateAgentWizard } from "@/features/create-agent/create-agent-wizard";

export const metadata: Metadata = { title: "Создать демо агента — Plumo" };

export default function CreateWizardPage() {
  return <CreateAgentWizard />;
}
