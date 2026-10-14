export function DashboardIcon({ name, size = 20 }: { name: "panel" | "chat" | "back" | "search" | "send" | "user" | "close" | "menu" | "plug" | "check"; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {name === "panel" && <><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M9 4v16" /></>}
    {name === "chat" && <path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5a9.5 9.5 0 0 1 19 0Z" />}
    {name === "back" && <path d="M19 12H5m6-6-6 6 6 6" />}
    {name === "search" && <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>}
    {name === "send" && <><path d="m3 3 18 9-18 9 4-9-4-9Z" /><path d="M7 12h14" /></>}
    {name === "user" && <><circle cx="12" cy="8" r="4" /><path d="M4 21v-2a8 8 0 0 1 16 0v2" /></>}
    {name === "close" && <path d="m6 6 12 12M6 18 18 6" />}
    {name === "menu" && <path d="M4 6h16M4 12h16M4 18h16" />}
    {name === "plug" && <><path d="M9 3v5m6-5v5M6 8h12v3a6 6 0 0 1-12 0V8Zm6 9v4" /></>}
    {name === "check" && <path d="m5 12 4 4L19 6" />}
  </svg>;
}
