// Where the API lives, and how this page proves it may call it.
//
// The daemon serves this bundle at its own loopback origin, so in production
// the API is same-origin and the base URL is simply `<origin>/api/v1`. The
// hardcoded :8000 default is gone with the desktop shell, which was the only
// thing that could be served from somewhere other than the daemon.
//
// The token arrives once, via the one-time code `coffer open` puts in the URL
// fragment (see `main.tsx`), and then lives in localStorage. It is never in a
// URL: a URL reaches browser history and the shell's scrollback, and this
// token unlocks the credential endpoints.

const TOKEN_STORAGE_KEY = "coffer.token";

type DevGlobals = {
  __COFFER_BASE_URL__?: string;
  __COFFER_TOKEN__?: string;
};

function devGlobals(): DevGlobals {
  return window as unknown as DevGlobals;
}

export function getCofferBaseUrl(): string {
  // 1. Vite dev server: the dev plugin reads ~/.coffer/daemon.json and injects
  //    the running daemon's origin, because :5173 is not the daemon.
  const injected = devGlobals().__COFFER_BASE_URL__;
  if (injected) return injected;
  // 2. Explicit build/dev override.
  const fromVite = import.meta.env.VITE_COFFER_BASE_URL as string | undefined;
  if (fromVite) return fromVite;
  // 3. Served by the daemon — same origin.
  return `${window.location.origin}/api/v1`;
}

export function getCofferToken(): string | null {
  const injected = devGlobals().__COFFER_TOKEN__;
  if (injected) return injected;
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    // Private mode / storage disabled. The app still renders; API calls will
    // surface the normal unauthenticated state.
    return null;
  }
}

export function setCofferToken(token: string | null): void {
  try {
    if (token === null) {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    } else {
      localStorage.setItem(TOKEN_STORAGE_KEY, token);
    }
  } catch {
    // Non-fatal: without storage the session lasts until reload.
  }
}
