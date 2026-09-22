// Where the API lives, and how this page proves it may call it.
//
// Two globals answer both questions, and every host converges on them. That
// convergence is the point: readers below never learn which host they are in,
// so a second host is a second *supplier* rather than a second path.
//
// Three suppliers write them:
//
//   - the daemon, which serves this bundle at its own loopback origin and
//     injects `window.__COFFER_TOKEN__` into the `index.html` it serves
//     (backend `webui.py`). No base URL: the API is same-origin.
//   - the Vite dev server's plugin, which injects the same token plus a base
//     URL read from `~/.coffer/daemon.json`, because :5173 is not the daemon.
//   - the desktop shell, whose window loads this bundle as a local asset, so
//     nobody injected anything into the document at all. `main.tsx` asks the
//     shell over IPC and calls `setDaemonConnection` below before the first
//     render. See docs/decisions/desktop-shell-over-a-shared-frontend.md.
//
// Nothing is persisted. A stored token was the whole bug: the daemon mints a
// new one on every start, so anything kept from a previous daemon is dead, and
// a page that trusted it got 401 on every call with no way to recover but
// re-running `coffer open`. Every supplier above reads from something the
// running daemon published, so none of them can hand over a dead token.

type InjectedGlobals = {
  __COFFER_BASE_URL__?: string;
  __COFFER_TOKEN__?: string;
};

function injectedGlobals(): InjectedGlobals {
  return window as unknown as InjectedGlobals;
}

/**
 * Where the API is, or `null` when nothing has said yet.
 *
 * `null` is not a failure — it is the honest answer for a page that no daemon
 * served and whose supplier has not arrived. The desktop shell's window is
 * exactly that: its document comes from a `tauri://` asset origin, and the
 * base URL reaches it over IPC a moment later. Falling back to that origin
 * looked harmless and was the whole bug: `tauri://localhost/api/v1` is a URL
 * the webview refuses to build a request from, so every query in the app
 * failed with an unreadable transport error ("The string did not match the
 * expected pattern") and the offline banner reported a perfectly healthy
 * daemon as offline. Callers turn `null` into `DAEMON_NOT_READY`, which the
 * banner already renders as "still starting — this clears itself".
 *
 * The origin fallback is kept for the hosts it is true for, and gated on the
 * one fact that makes it true: an http(s) document was served by something,
 * and the only thing that serves this bundle over http is the daemon.
 */
export function getCofferBaseUrl(): string | null {
  // 1. Vite dev server: the dev plugin reads ~/.coffer/daemon.json and injects
  //    the running daemon's origin, because :5173 is not the daemon. The
  //    desktop shell writes the same global once its handshake lands.
  const injected = injectedGlobals().__COFFER_BASE_URL__;
  if (injected) return injected;
  // 2. Explicit build/dev override.
  const fromVite = import.meta.env.VITE_COFFER_BASE_URL as string | undefined;
  if (fromVite) return fromVite;
  // 3. Served by the daemon — same origin.
  const { origin } = window.location;
  if (origin.startsWith("http://") || origin.startsWith("https://")) {
    return `${origin}/api/v1`;
  }
  // 4. Nobody served this page and nobody has supplied an address yet.
  return null;
}

export function getCofferToken(): string | null {
  // Empty counts as absent: a page that was served before the daemon published
  // a token carries no script at all, and tests blank the global to stand in
  // for that. Either way the answer is "this page has no credential".
  return injectedGlobals().__COFFER_TOKEN__ || null;
}

/**
 * Write the connection globals the desktop host has no document to carry.
 *
 * Called pre-render by `main.tsx` at launch, and again after the offline
 * banner's Restart succeeds — the daemon mints a fresh token on every start,
 * so the launch-time copy is revoked the moment a new daemon comes up.
 * Callers that memoised the base URL (the openapi-fetch client) must also
 * `resetApiClient()`; the token itself is read per-request and needs no reset.
 */
export function setDaemonConnection(baseUrl: string, token: string): void {
  const w = injectedGlobals();
  w.__COFFER_BASE_URL__ = baseUrl;
  w.__COFFER_TOKEN__ = token;
}
