// Which backend routes the browser may reach through /api/plumo/*.
// The proxy is not an open door to FastAPI: anything not listed here is refused.
// Pure module (no Next.js imports) so tests can run it with plain Node.

const id = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";

const allowed: Record<string, RegExp[]> = {
  GET: [
    /^auth\/me$/,
    /^integrations$/,
    /^conversations$/,
    new RegExp(`^conversations/${id}$`),
    new RegExp(`^conversations/${id}/messages$`),
    new RegExp(`^outbound-messages/${id}$`),
    new RegExp(`^customers/${id}(/history)?$`),
  ],
  POST: [
    /^integrations\/(telegram|instagram)\/connect$/,
    new RegExp(`^integrations/${id}/(check|disconnect)$`),
    new RegExp(`^conversations/${id}/(takeover|resume|messages|read)$`),
    new RegExp(`^outbound-messages/${id}/resolve$`),
  ],
  PATCH: [new RegExp(`^integrations/${id}$`)],
};

export function isAllowedRoute(method: string, path: string): boolean {
  if (path.includes("..") || path.includes("//")) return false;
  return (allowed[method.toUpperCase()] ?? []).some(pattern => pattern.test(path));
}

// Query keys forwarded with GET; anything else is dropped.
export const allowedQuery = new Set(["channel", "mode", "q", "cursor", "limit", "before"]);

export function forwardQuery(search: URLSearchParams): string {
  const kept = new URLSearchParams();
  search.forEach((value, key) => { if (allowedQuery.has(key)) kept.append(key, value.slice(0, 300)); });
  const text = kept.toString();
  return text ? `?${text}` : "";
}

// A state-changing request must come from our own page: same Origin and our custom header,
// which a cross-site form cannot send without a CORS preflight.
export function isSameOriginWrite(method: string, origin: string | null, host: string | null, marker: string | null): boolean {
  if (method === "GET" || method === "HEAD") return true;
  if (marker !== "1" || !origin || !host) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}
