// Where the API lives, and how this page proves it may call it.
//
// The daemon serves this bundle at its own loopback origin, so in production
// the API is same-origin and the base URL is simply `<origin>/api/v1`. The
// hardcoded :8000 default is gone with the desktop shell, which was the only
// thing that could be served from somewhere other than the daemon.
//
// The token arrives in the page itself: whoever served this document set
// `window.__COFFER_TOKEN__` in the head before the bundle ran — the daemon
// injects it into the `index.html` it serves (backend `webui.py`), and the
// Vite dev server's plugin does the same from `~/.coffer/daemon.json` because
// :5173 is not the daemon. Either way the value is the token of the daemon
// that is running right now.
//
// Nothing is persisted. A stored token was the whole bug: the daemon mints a
// new one on every start, so anything kept from a previous daemon is dead, and
// a page that trusted it got 401 on every call with no way to recover but
// re-running `coffer open`. A page that reads the token from its own document
// cannot go stale — a reload re-fetches the document.

type InjectedGlobals = {
  __COFFER_BASE_URL__?: string;
  __COFFER_TOKEN__?: string;
};

function injectedGlobals(): InjectedGlobals {
  return window as unknown as InjectedGlobals;
}

export function getCofferBaseUrl(): string {
  // 1. Vite dev server: the dev plugin reads ~/.coffer/daemon.json and injects
  //    the running daemon's origin, because :5173 is not the daemon.
  const injected = injectedGlobals().__COFFER_BASE_URL__;
  if (injected) return injected;
  // 2. Explicit build/dev override.
  const fromVite = import.meta.env.VITE_COFFER_BASE_URL as string | undefined;
  if (fromVite) return fromVite;
  // 3. Served by the daemon — same origin.
  return `${window.location.origin}/api/v1`;
}

export function getCofferToken(): string | null {
  // Empty counts as absent: a page that was served before the daemon published
  // a token carries no script at all, and tests blank the global to stand in
  // for that. Either way the answer is "this page has no credential".
  return injectedGlobals().__COFFER_TOKEN__ || null;
}
