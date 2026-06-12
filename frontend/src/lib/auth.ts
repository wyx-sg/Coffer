const DEFAULT_BASE = "http://127.0.0.1:8000/api/v1";

export function getCofferBaseUrl(): string {
  // 1. Tauri-injected env (production via desktop app)
  const fromTauri = (window as unknown as Record<string, unknown>).__COFFER_BASE_URL__ as
    | string
    | undefined;
  if (fromTauri) return fromTauri;
  // 2. Vite env (dev)
  const fromVite = import.meta.env.VITE_COFFER_BASE_URL as string | undefined;
  if (fromVite) return fromVite;
  return DEFAULT_BASE;
}

export function getCofferToken(): string | null {
  // 1. Tauri-injected
  const fromTauri = (window as unknown as Record<string, unknown>).__COFFER_TOKEN__ as
    | string
    | undefined;
  if (fromTauri) return fromTauri;
  // 2. localStorage (dev fallback)
  return localStorage.getItem("coffer.token");
}

/**
 * Overwrite the Tauri-injected connection globals. Written pre-render by
 * main.tsx (desktop launch) and again after a daemon restart — the daemon
 * mints a fresh token on every start, so the launch-time copy is revoked
 * the moment "Restart daemon" succeeds. Callers that memoised the base URL
 * (the openapi-fetch client) must also resetApiClient().
 */
export function setDaemonConnection(baseUrl: string, token: string): void {
  const w = window as unknown as Record<string, unknown>;
  w.__COFFER_BASE_URL__ = baseUrl;
  w.__COFFER_TOKEN__ = token;
}

export function setCofferToken(token: string | null): void {
  if (token === null) {
    localStorage.removeItem("coffer.token");
  } else {
    localStorage.setItem("coffer.token", token);
  }
}
