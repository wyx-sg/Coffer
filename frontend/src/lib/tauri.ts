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
 * Install a connection the shell handed over: publish it on the two
 * connection globals and drop the memoised API client.
 *
 * Both steps or neither. The client captures the base URL when it is built,
 * so installing without the reset would leave the app calling whatever address
 * it had when the first query fired — for the desktop host, none at all.
 *
 * Two suppliers call this: the launch handshake below, and a restart, which
 * returns the connection of the daemon it waited for.
 */
export function applyDaemonConnection(info: DaemonInfo): void {
  setDaemonConnection(info.baseUrl, info.token);
  resetApiClient();
}

/**
 * Do the handshake and install its result.
 *
 * Throws whatever the IPC threw; `credentialDesktopHost` below decides what a
 * failure means.
 */
export async function connectToShellDaemon(): Promise<void> {
  applyDaemonConnection(await getDaemonInfo());
}

/**
 * Delays before each retry of the launch handshake, in milliseconds; the last
 * one repeats for as long as it takes.
 */
export const HANDSHAKE_RETRY_DELAYS_MS = [1_000, 2_000, 5_000, 10_000, 30_000];

/** The delay before attempt `n + 1`, given `n` attempts have failed. */
export function handshakeRetryDelay(failures: number): number {
  const i = Math.min(Math.max(failures, 1), HANDSHAKE_RETRY_DELAYS_MS.length) - 1;
  return HANDSHAKE_RETRY_DELAYS_MS[i];
}

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

/**
 * Keep asking the shell for a connection until it gives one, then hand control
 * back to `onConnected`.
 *
 * Retrying is the whole point. A handshake is one attempt at a thing with a
 * deadline — the shell gives a daemon it started a bounded time to answer —
 * and a real vault's daemon spends seconds unpacking, migrating and starting
 * its upstreams before it accepts a request. When an attempt lost that race
 * the page was left with no address to call and no way to get one: its own
 * status poll had nothing to poll, so the offline banner stayed up over a
 * daemon that had been serving happily for a minute, and the only way out was
 * the banner's Restart button — which worked purely because it ran the
 * handshake again. This does that, without the user.
 *
 * It does not stop trying. Each attempt is cheap when a daemon is up (the
 * shell probes and attaches), and the shell refuses to start a second daemon
 * beside a running one, so a loop that settles at one attempt every thirty
 * seconds is also the recovery for "the user has just fixed their install".
 *
 * Outside Tauri there is nothing to ask: the browser hosts were credentialed
 * by whoever served the document.
 */
export async function credentialDesktopHost(
  onConnected: () => void | Promise<void>,
  deps: { connect?: () => Promise<void>; wait?: (ms: number) => Promise<void> } = {},
): Promise<void> {
  if (!isTauri()) return;
  const connect = deps.connect ?? connectToShellDaemon;
  const wait = deps.wait ?? sleep;
  for (let failures = 0; ; failures += 1) {
    try {
      await connect();
      await onConnected();
      return;
    } catch (e) {
      // Not fatal, and not silent either: the app is already on screen with
      // its offline banner, and the shell logs its own side of the failure to
      // ~/.coffer/logs/daemon.log.
      console.error("Coffer: could not get daemon info from the desktop shell", e);
    }
    await wait(handshakeRetryDelay(failures + 1));
  }
}

export interface RestartResult extends DaemonInfo {
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
 *
 * The shell waits for the replacement to answer and returns its connection
 * with the PID, so the caller installs that rather than handshaking again. A
 * second handshake here is what used to start a second daemon: it arrived
 * before the new one had bound a port, and the handshake answers "no daemon"
 * by spawning one.
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
