// Only fixed diagnostic categories leave the server; never include raw errors or config values.
export type ConnectionFailure = "backend_url_missing" | "backend_url_invalid" | "backend_url_local" | "backend_key_invalid" | "backend_dns_error" | "backend_connection_refused" | "backend_timeout" | "backend_tls_error" | "backend_network_error";

export class BackendConnectionError extends Error {
  readonly reason: ConnectionFailure;
  constructor(reason: ConnectionFailure) { super(reason); this.reason = reason; }
}

export function backendConnection(rawUrl: string | undefined, rawKey: string | undefined, deployed: boolean) {
  const configured = rawUrl?.trim();
  if (!configured && deployed) throw new BackendConnectionError("backend_url_missing");
  const base = (configured || "http://127.0.0.1:8000").replace(/\/+$/, "");
  let url: URL;
  try { url = new URL(base); } catch { throw new BackendConnectionError("backend_url_invalid"); }
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new BackendConnectionError("backend_url_invalid");
  if (deployed && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) throw new BackendConnectionError("backend_url_local");
  const key = rawKey?.trim();
  if (key && /[^\x20-\x7e]/.test(key)) throw new BackendConnectionError("backend_key_invalid");
  return { base, key };
}

export function connectionFailure(error: unknown): ConnectionFailure {
  if (error instanceof BackendConnectionError) return error.reason;
  let current = error;
  for (let depth = 0; depth < 5 && current && typeof current === "object"; depth++) {
    const item = current as { name?: unknown; code?: unknown; cause?: unknown };
    if (item.name === "TimeoutError" || item.name === "AbortError" || ["ETIMEDOUT", "UND_ERR_CONNECT_TIMEOUT", "UND_ERR_HEADERS_TIMEOUT"].includes(String(item.code))) return "backend_timeout";
    if (["ENOTFOUND", "EAI_AGAIN"].includes(String(item.code))) return "backend_dns_error";
    if (item.code === "ECONNREFUSED") return "backend_connection_refused";
    if (["CERT_HAS_EXPIRED", "DEPTH_ZERO_SELF_SIGNED_CERT", "UNABLE_TO_VERIFY_LEAF_SIGNATURE", "ERR_TLS_CERT_ALTNAME_INVALID"].includes(String(item.code))) return "backend_tls_error";
    current = item.cause;
  }
  return "backend_network_error";
}
