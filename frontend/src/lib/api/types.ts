// Shapes of the Plumo dashboard API (backend/docs/openapi.json, tags auth, integrations, dialogs).

export type ApiErrorBody = { error?: string; code?: string; message?: string; correlation_id?: string | null };

export type Operator = { id: string; email: string; display_name: string; business: { id: string; name: string } };
export type Session = { operator: Operator; expires_at: string; ai_mode: string };

export type ConnectionStatus = "not_connected" | "connecting" | "connected" | "action_required" | "error" | "disconnected";
export type IntegrationChannel = "telegram" | "instagram";

export type Account = { external_id: string; display_name: string; username: string | null; link: string | null };
export type Connection = {
  verification?: { state: string; link: string | null; expires_at: string | null; verified_at: string | null; error: string | null } | null;
  id: string;
  channel: IntegrationChannel;
  status: ConnectionStatus;
  auth_method: string;
  credential_ref: string;
  account: Account;
  agent_enabled: boolean;
  version: number;
  last_check_at: string | null;
  last_check_ok: boolean | null;
  last_event_at: string | null;
  last_error: { code: string; message: string; at: string | null } | null;
  details: Record<string, string | number | boolean>;
  created_at: string;
  updated_at: string;
  disconnected_at: string | null;
};
export type ChannelIntegration = {
  channel: IntegrationChannel;
  status: ConnectionStatus;
  connection: Connection | null;
  credentials: { ref: string; label: string }[];
  requirements: Record<string, boolean>;
  webhook_url: string | null;
};
export type IntegrationsResponse = { channels: ChannelIntegration[]; ai_mode: string };

export type Limits = { day: string; calls: number; calls_limit: number; spent_usd: number; limit_usd: number };

export type ManagerStatus = "not_configured" | "waiting_code" | "awaiting_confirmation" | "ready" | "needs_attention";
export type ManagerChat = { label: string; at: string | null };
export type ManagerNotifications = {
  status: ManagerStatus;
  recipient: ManagerChat | null;
  candidate: ManagerChat | null;
  attention: string | null;
  code_expires_at: string | null;
  bot_username: string | null;
  service_bot_configured: boolean;
};
export type ManagerLink = ManagerNotifications & { command: string; link: string | null };
export type ManagerConfirm = ManagerNotifications & { control_delivery: "sent" | "failed" | "rejected" };

export type DialogMode = "ai" | "waiting" | "human";
export type DeliveryStatus = "queued" | "sending" | "sent" | "failed" | "unknown" | "cancelled";
export type Delivery = { id: string; status: DeliveryStatus; attempts: number; error_code: string | null; sent_at: string | null; updated_at: string };

export type DialogItem = {
  id: string;
  channel: string;
  mode: DialogMode;
  mode_version: number;
  customer: { id: string; name: string | null; handle: string | null; phone: string | null; language: string };
  connection_id: string | null;
  last_message: { text: string; role: string; at: string } | null;
  activity_at: string;
  unread: number;
  last_seq: number | null;
};
export type DialogList = { items: DialogItem[]; next_cursor: string | null };

export type DialogMessage = {
  id: string;
  seq: number | null;
  role: "user" | "assistant" | "manager" | "system";
  text: string;
  timestamp: string;
  author: string | null;
  event: string | null;
  unsupported: string | null;
  /** The customer sent a voice message; `text` is its transcript when `transcribed`. */
  voice?: { duration_s: number | null; transcribed: boolean } | null;
  delivery: Delivery | null;
};

export type ReplyState = {
  allowed: boolean;
  reason: string | null;
  max_chars: number | null;
  max_bytes: number | null;
  window_expires_at: string | null;
};

export type DialogDetail = {
  dialog: DialogItem;
  messages: DialogMessage[];
  older_cursor: string | null;
  customer: { id: string; phone: string | null; contact_phone: string | null; language: string; status: string; need: string | null };
  summary: { summary: string; need: string | null; language: string; status: string; important_facts: string[]; updated_at: string } | null;
  handoff: {
    id: string; reason: string; priority: string; status: string; summary: string; created_at: string;
    notify_status: "queued" | "sending" | "sent" | "failed" | "unknown" | "cancelled" | null; notify_error: string | null; notified_at: string | null;
  } | null;
  connection: { id: string; channel: string; status: ConnectionStatus; agent_enabled: boolean; account: Account } | null;
  reply: ReplyState;
};

export type DialogMessages = { messages: DialogMessage[]; older_cursor: string | null };
export type ManagerSend = { message: DialogMessage; delivery: Delivery; created: boolean };
export type DialogState = { id: string; mode: DialogMode; mode_version: number };
