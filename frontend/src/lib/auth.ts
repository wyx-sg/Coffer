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

export function setCofferToken(token: string | null): void {
  if (token === null) {
    localStorage.removeItem("coffer.token");
  } else {
    localStorage.setItem("coffer.token", token);
  }
}
