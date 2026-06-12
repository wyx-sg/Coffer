/**
 * Helpers for detecting Tauri context + invoking Tauri commands.
 *
 * In dev (Vite on localhost:5173 in a browser), Tauri APIs aren't available
 * and these helpers return safe fallbacks. In production (Tauri WebView)
 * they invoke the real commands.
 */

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
 * Ask the Tauri shell for the running daemon's base URL + token. The desktop
 * app loads the frontend as bundled static assets, so the frontend can't read
 * ~/.coffer/daemon.json itself — the shell ensures the bundled daemon is
 * running (detect-or-spawn) and returns its connection info. Throws outside
 * Tauri (browser dev), where the token comes from Vite env / localStorage.
 */
export async function getDaemonInfo(): Promise<DaemonInfo> {
  if (!isTauri()) {
    throw new Error("get_daemon_info is only available inside the Tauri app");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<DaemonInfo>("get_daemon_info");
}

export async function setAutostartEnabled(enabled: boolean): Promise<boolean> {
  if (!isTauri()) {
    // Dev fallback — pretend success but mark the toggle as a no-op
    return enabled;
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("set_autostart_enabled", { enabled });
}

export async function getAutostartEnabled(): Promise<boolean> {
  if (!isTauri()) {
    return false;
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("get_autostart_enabled");
}

export interface RestartResult {
  /** PID of the newly-spawned daemon process. */
  pid: number;
  /** true when the daemon was successfully spawned. */
  started: boolean;
}

/**
 * Ask Tauri to spawn the bundled coffer-daemon binary detached so it
 * survives the desktop app.  Throws when running outside Tauri (browser dev).
 */
export async function restartDaemon(): Promise<RestartResult> {
  if (!isTauri()) {
    throw new Error("restart_daemon is only available inside the Tauri app");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<RestartResult>("restart_daemon");
}

/**
 * Whether the running daemon's reported version matches the version this app
 * build expects. The desktop app bundles its daemon, so a mismatch means the
 * app is talking to a stale daemon a previous app version left detached and
 * listening (P2: version skew). Returns `true` outside Tauri (browser dev),
 * where there is no app/daemon pairing to check.
 */
export async function daemonVersionMatches(daemonVersion: string): Promise<boolean> {
  if (!isTauri()) {
    return true;
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("daemon_version_matches", { daemonVersion });
}
