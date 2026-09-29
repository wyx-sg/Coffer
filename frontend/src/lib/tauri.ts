// The desktop shell, seen from the page it hosts.
//
// One frontend build serves two hosts. In a browser every helper here returns
// a safe fallback or throws. Inside the Tauri WebView the page can ask the
// shell where the daemon is, to spawn one, whether its version pairs with this
// build, to label the tray in the chosen language, to check for and install an
// update (`shellUpdates.ts`, through `shellInvoke`) — and for the presence-gated
// actions (reveal a secret, write a key backup, approve an approval), each
// behind a Touch ID / password check in the shell. In a browser those reject
// and the page offers "Open in Coffer app". Components ask
// `presenceAvailable()`, never `isTauri()` directly.
//
// Keep this list short. The shell owns only what a browser cannot do for
// itself; native file dialogs and "reveal in Finder" deliberately do NOT live
// here — they go through daemon HTTP routes, which a WebView calls exactly
// like a tab does. See docs/decisions/desktop-shell-over-a-shared-frontend.md.

import { setDaemonConnection } from "./auth";
import { resetApiClient } from "./api/client";
import type { components } from "./api/generated/credentials";

export function isTauri(): boolean {
  // @ts-expect-error — Tauri injects __TAURI_INTERNALS__ in its WebView
  return typeof window !== "undefined" && window.__TAURI_INTERNALS__ !== undefined;
}

/**
 * Invoke one of the shell's own commands. Callers decide first whether they
 * are in the shell — through `isTauri()` here, or a predicate this module
 * exports — so nothing outside this module imports the Tauri API.
 */
export async function shellInvoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const { invoke } = await import("@tauri-apps/api/core");
  return args === undefined ? invoke<T>(command) : invoke<T>(command, args);
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
  if (!isTauri()) throw new Error("get_daemon_info is only available inside the Tauri app");
  return shellInvoke<DaemonInfo>("get_daemon_info");
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
 * Retrying is the whole point. A handshake is one attempt with a deadline,
 * and a real vault's daemon spends seconds unpacking, migrating and starting
 * its upstreams before it answers. An attempt that lost that race used to leave
 * the page with no address and the offline banner up over a serving daemon,
 * until the user pressed Restart — which only worked because it ran the
 * handshake again. This does that, without the user, and never stops: each
 * attempt is cheap when a daemon is up, and the shell refuses to start a
 * second one beside it, so it is also the recovery for a fixed install.
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
 * The shell waits for the replacement and returns its connection with the
 * PID; the caller installs that rather than handshaking again, which used to
 * arrive before the new daemon had bound and so spawn a second one.
 */
export async function restartDaemon(): Promise<RestartResult> {
  if (!isTauri()) throw new Error("restart_daemon is only available inside the Tauri app");
  return shellInvoke<RestartResult>("restart_daemon");
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
  return shellInvoke<boolean>("daemon_version_matches", { daemonVersion });
}

/** The slice of an i18next instance `followLanguageInShell` uses. */
export interface LanguageSource {
  language: string | undefined;
  on(event: "languageChanged", callback: (lng: string) => void): void;
}

/**
 * Tell the shell which interface language to label its tray in.
 *
 * The choice lives in the webview's storage, where the shell cannot read it,
 * so the page reports it. A no-op outside Tauri: a browser has no tray.
 */
export async function setShellLanguage(language: string): Promise<void> {
  if (!isTauri()) return;
  await shellInvoke("set_ui_language", { language });
}

/**
 * Keep the tray in the interface language: report it now, and again on every
 * switch, so the tray relabels without a restart. A failed report leaves the
 * tray in its previous language, which is not worth an error on the page.
 */
export function followLanguageInShell(
  i18n: LanguageSource,
  report: (language: string) => Promise<void> = setShellLanguage,
): void {
  if (!isTauri()) return;
  const tell = (language: string) => {
    report(language).catch((e: unknown) => {
      console.error("Coffer: could not tell the desktop shell the interface language", e);
    });
  };
  if (i18n.language) tell(i18n.language);
  i18n.on("languageChanged", tell);
}

// ---------------------------------------------------------------------------
// Presence-gated actions (spec desktop-app "Release plaintext and approvals
// only after a presence check in the shell")
// ---------------------------------------------------------------------------

/** A change waiting for a present human — what `approve_pending` answers. */
type Approval = components["schemas"]["ApprovalOut"];

/** Thrown by every presence-gated action outside the desktop shell. */
export class PresenceUnavailableError extends Error {
  constructor(action: string) {
    super(`${action} is only available in the Coffer desktop app`);
    this.name = "PresenceUnavailableError";
  }
}

/** True only in the desktop shell: show the control, else "Open in Coffer app". */
export function presenceAvailable(): boolean {
  return isTauri();
}

/** What `presence_mode` reports about the daemon the shell signs for. */
export interface PresenceMode {
  /** A development build keeps its master key in a file any local process can
   *  read, so a grant can be forged there and the boundary does not hold. */
  development: boolean;
}

/** Ask the shell whether the daemon is a development build. Throws outside it. */
export async function presenceMode(): Promise<PresenceMode> {
  if (!isTauri()) throw new PresenceUnavailableError("presence_mode");
  return shellInvoke<PresenceMode>("presence_mode");
}

/** Reveal one secret's plaintext after a presence check. Throws outside the shell. */
export async function revealSecret(secretRef: string): Promise<string> {
  if (!isTauri()) throw new PresenceUnavailableError("reveal_secret");
  return shellInvoke<string>("reveal_secret", { secretRef });
}

/** Where the shell wrote a master key backup, and the key it holds. */
export interface MasterKeyBackup {
  path: string;
  fingerprint: string;
}

/** Write a master key backup after a presence check; the key never reaches the page. */
export async function exportMasterKeyBackup(): Promise<MasterKeyBackup> {
  if (!isTauri()) throw new PresenceUnavailableError("export_master_key_backup");
  return shellInvoke<MasterKeyBackup>("export_master_key_backup");
}

/** Approve one pending approval after a presence check. Throws outside the shell. */
export async function approvePending(approvalId: string): Promise<Approval> {
  if (!isTauri()) throw new PresenceUnavailableError("approve_pending");
  return shellInvoke<Approval>("approve_pending", { approvalId });
}

/** The event the shell emits when it sees a pending approval it has not announced. */
export const APPROVALS_EVENT = "coffer://approvals";

/**
 * Call `callback` with each payload the shell emits on `event`; a no-op
 * outside the shell. Returns the unsubscribe.
 */
export function onShellEvent<T>(event: string, callback: (payload: T) => void): () => void {
  if (!isTauri()) return () => {};
  let unlisten: (() => void) | null = null;
  let cancelled = false;
  void import("@tauri-apps/api/event")
    .then(({ listen }) => listen<T>(event, (e) => callback(e.payload)))
    .then((stop) => {
      if (cancelled) stop();
      else unlisten = stop;
    })
    .catch((e: unknown) => {
      console.error(`Coffer: could not listen for ${event} from the desktop shell`, e);
    });
  return () => {
    cancelled = true;
    unlisten?.();
  };
}

/** Call `callback` on each approval the shell announces; a no-op outside the shell. */
export function onApprovalsEvent(callback: () => void): () => void {
  return onShellEvent(APPROVALS_EVENT, () => callback());
}
