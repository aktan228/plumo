export type IntegrationChannel = "WhatsApp" | "Telegram" | "Instagram";
export type ChannelSetup = { method: string; access: boolean; manager: boolean };
export const methods: Record<IntegrationChannel, string[]> = {
  WhatsApp: ["business-app", "cloud"], Telegram: ["bot"], Instagram: ["business", "creator"],
};
export function initialSetup(channel: IntegrationChannel): ChannelSetup {
  return { method: methods[channel][0], access: false, manager: false };
}
export function validSetup(channel: IntegrationChannel, setup: ChannelSetup): boolean {
  return methods[channel].includes(setup.method) && setup.access && setup.manager;
}

// A saved configuration is not proof of an active provider connection.
export function setupStatus(setup?: ChannelSetup, connected = false): "not-connected" | "needs-action" | "connected" {
  if (connected) return "connected";
  return setup ? "needs-action" : "not-connected";
}
