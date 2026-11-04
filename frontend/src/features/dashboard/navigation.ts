export const dashboardGroups = [
  { ru: "Основное", en: "Main", items: [
    { id: "chats", ru: "Диалоги", en: "Chats", icon: "chat", href: "#chats" },
    { id: "knowledge", ru: "База знаний", en: "Knowledge Base", icon: "book", href: "#knowledge" },
    { id: "testing", ru: "Тестирование", en: "Testing", icon: "testing", href: "#testing" },
    { id: "improvements", ru: "Улучшения", en: "Improvement", icon: "edit", href: "#improvements" },
    { id: "scenarios", ru: "Сценарии", en: "Scenarios", icon: "branch", href: "#scenarios" },
    { id: "settings", ru: "Настройки", en: "Settings", icon: "settings", href: "#settings" },
  ] },
  { ru: "Клиенты", en: "Customers", items: [
    { id: "customers", ru: "Клиенты", en: "Customers", icon: "customers", href: "#customers" },
    { id: "statistics", ru: "Статистика", en: "Statistics", icon: "statistics", href: "#statistics" },
  ] },
  { ru: "Подключение", en: "Connection", items: [
    { id: "integrations", ru: "Интеграции", en: "Integrations", icon: "integrations", href: "#integrations" },
  ] },
] as const;

export const plannedSections = [
  { ru: "Инструменты и расширения", en: "Tools and extensions" },
  { ru: "Рассылки, голос и оплата", en: "Broadcasts, voice and payments" },
] as const;

export type DashboardView = "chats" | "customers" | "statistics" | "scenarios" | "improvements" | "knowledge" | "settings" | "testing" | "integrations" | "help";
export type DashboardDestination = DashboardView;

const conversationId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function dashboardConversation(search: string): string | null {
  const id = new URLSearchParams(search).get("conversation");
  return id && conversationId.test(id) ? id : null;
}
export function conversationHref(id: string): string {
  return conversationId.test(id) ? `/dashboard?conversation=${encodeURIComponent(id)}#chats` : "/dashboard#chats";
}
export function knowledgeHref(id: string): string {
  return conversationId.test(id) ? `/dashboard?source=${encodeURIComponent(id)}#knowledge` : "/dashboard#knowledge";
}
export function customerHref(id: string): string {
  return conversationId.test(id) ? `/dashboard?customer=${encodeURIComponent(id)}#customers` : "/dashboard#customers";
}
export function improvementHref(id: string): string {
  return conversationId.test(id) ? `/dashboard?issue=${encodeURIComponent(id)}#improvements` : "/dashboard#improvements";
}
export function testingHref(id: string): string {
  return conversationId.test(id) ? `/dashboard?test=${encodeURIComponent(id)}#testing` : "/dashboard#testing";
}
export function dashboardIssue(search: string): string | null {
  const id = new URLSearchParams(search).get("issue");
  return id && conversationId.test(id) ? id : null;
}
export function dashboardTest(search: string): string | null {
  const id = new URLSearchParams(search).get("test");
  return id && conversationId.test(id) ? id : null;
}
export function dashboardCustomer(search: string): string | null {
  const id = new URLSearchParams(search).get("customer");
  return id && conversationId.test(id) ? id : null;
}

/** Preserve the skip-link target; old section URLs have a useful destination. */
export function dashboardDestination(hash: string): DashboardDestination | null {
  const id = hash.replace(/^#/, "");
  if (id === "workspace") return null;
  if (!id || id === "chats") return "chats";
  if (id === "scenarios" || id === "improvements" || id === "statistics" || id === "customers" || id === "settings" || id === "knowledge" || id === "testing" || id === "integrations" || id === "help") return id;
  return "help";
}
