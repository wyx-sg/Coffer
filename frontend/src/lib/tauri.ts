// The desktop shell, seen from the page it hosts.
//
// One frontend build serves two hosts. In a browser — daemon-served or the
// Vite dev server — none of this applies and every helper here returns a safe
// fallback or throws, so the browser path never depends on a shell being
// there. Inside the Tauri WebView the same build gets a native host, and these
// are the three things it can ask that host for: where the daemon is, spawn one,
// and whether the one answering is the version this build pairs with.
//
// Keep this list short. The shell owns only what a browser cannot do for
// itself; native file dialogs and "reveal in Finder" deliberately do NOT live
// here — they go through daemon HTTP routes, which a WebView calls exactly
// like a tab does. See docs/decisions/desktop-shell-over-a-shared-frontend.md.

import { setDaemonConnection } from "./auth";
import { resetApiClient } from "./api/client";

export function isTauri(): boolean {
  // @ts-expect-error — Tauri injects __TAURI_INTERNALS__ in its WebView
  return typeof window !== "undefined" && window.__TAURI_INTERNALS__ !== undefined;
}

export interface DaemonInfo {
  /** `http://127.0.0.1:<port>/api/v1` */
  baseUrl: string;
  token: string;
}

/**
 * Ask the shell for the running daemon's base URL + token.
 *
 * The desktop window loads the frontend as a local asset, so nobody injected
 * `window.__COFFER_TOKEN__` into the document the way the daemon does for a
 * browser — and the page cannot read `~/.coffer/daemon.json` itself. The shell
 * detect-or-spawns a daemon and hands back its connection info; `main.tsx`
 * writes it onto the same two globals the browser path uses, so there is one
 * credential path with two suppliers. Throws outside Tauri.
 */
export async function getDaemonInfo(): Promise<DaemonInfo> {
  if (!isTauri()) {
    throw new Error("get_daemon_info is only available inside the Tauri app");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<DaemonInfo>("get_daemon_info");
}

/**
 * Do the handshake and install its result: ask the shell where the daemon is,
 * publish that on the connection globals, and drop the memoised API client.
 *
 * All three steps or none. The client captures the base URL when it is built,
 * so a handshake that skipped the reset would leave the app calling whatever
 * origin it had guessed first — for the desktop host a `tauri://` asset origin
 * with no daemon behind it. That is the kind of bug a second copy of these
 * lines grows, so both callers share this one: `main.tsx` at launch, and the
 * offline banner after a restart.
 *
 * Throws whatever the IPC threw — the callers want different things from a
 * failure (log and render anyway vs. tell the user the restart half-worked),
 * so neither is served by swallowing it here.
 */
export async function connectToShellDaemon(): Promise<void> {
  const info = await getDaemonInfo();
  setDaemonConnection(info.baseUrl, info.token);
  resetApiClient();
}

export interface RestartResult {
  /** PID of the newly-spawned daemon process. */
  pid: number;
  /** true when the daemon was successfully spawned. */
  started: boolean;
}

/**
 * Ask the shell to spawn a daemon, detached so it survives the app.
 *
 * Only the desktop host can offer this: in a browser the page is served *by*
 * the daemon, so a daemon that is down cannot serve the button that would
 * restart it. Throws outside Tauri.
 */
export async function restartDaemon(): Promise<RestartResult> {
  if (!isTauri()) {
    throw new Error("restart_daemon is only available inside the Tauri app");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<RestartResult>("restart_daemon");
}

/**
 * Whether the running daemon's reported version is the one this app build
 * expects.
 *
 * The app pairs with a daemon, so a mismatch means it reused one an earlier
 * app version left detached and listening — reachable, answering, and stale.
 * Returns `true` (i.e. "no skew") outside Tauri: a browser is served by
 * whichever daemon is running and has no pairing to be out of step with.
 */
export async function daemonVersionMatches(daemonVersion: string): Promise<boolean> {
  if (!isTauri()) {
    return true;
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("daemon_version_matches", { daemonVersion });
}
