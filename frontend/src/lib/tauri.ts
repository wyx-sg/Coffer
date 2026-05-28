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
