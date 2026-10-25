import type { ChannelIntegration, ConnectionStatus } from "@/lib/api/types";

// WhatsApp keeps its demo wizard (no live connection in this version).
export type DemoChannel = "WhatsApp";
export type ChannelSetup = { method: string; access: boolean; manager: boolean };
export const methods: Record<DemoChannel, string[]> = { WhatsApp: ["business-app", "cloud"] };
export function initialSetup(channel: DemoChannel): ChannelSetup {
  return { method: methods[channel][0], access: false, manager: false };
}

type Locale = "ru" | "en";

const statusLabels: Record<Locale, Record<ConnectionStatus, string>> = {
  ru: { not_connected: "Не подключён", connecting: "Подключается", connected: "Подключён", action_required: "Требуется действие", error: "Ошибка", disconnected: "Отключён" },
  en: { not_connected: "Not connected", connecting: "Connecting", connected: "Connected", action_required: "Action required", error: "Error", disconnected: "Disconnected" },
};
export function statusLabel(status: ConnectionStatus, locale: Locale): string {
  return statusLabels[locale][status];
}

export function statusTone(status: ConnectionStatus): "ok" | "warn" | "error" | "idle" {
  if (status === "connected") return "ok";
  if (status === "action_required" || status === "connecting") return "warn";
  if (status === "error") return "error";
  return "idle";
}

/**
 * The status a card shows. Without any server credential for the channel it is "action required":
 * the team must prepare access first; a click cannot connect anything.
 */
export function cardStatus(item: ChannelIntegration): ConnectionStatus {
  if (item.connection && item.connection.status !== "disconnected") return item.connection.status;
  if ((item.channel !== "telegram" && !item.credentials.length) || missingRequirements(item).length) return "action_required";
  return item.connection ? "disconnected" : "not_connected";
}

/** Server settings that are missing for this channel, by name (values are never sent). */
export function missingRequirements(item: ChannelIntegration): string[] {
  return Object.entries(item.requirements).filter(([, ready]) => !ready).map(([name]) => name);
}

export function canConnect(item: ChannelIntegration): boolean {
  return (item.channel === "telegram" || item.credentials.length > 0) && missingRequirements(item).length === 0;
}

/** Live connection = connected now; the agent switch and the last check are shown separately. */
export function isLive(item: ChannelIntegration): boolean {
  return item.connection?.status === "connected";
}
