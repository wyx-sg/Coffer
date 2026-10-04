// frontend/src/lib/shellUpdates.ts — the desktop shell's update check, seen
// from the page (spec web-ui "Check for and install updates on Settings ›
// About").
//
// The check, the download, the signature verification and the relaunch are
// the shell's (spec desktop-app "Check for updates against a signed release
// manifest"); the page only renders the record the shell reports and asks it
// to act. Everything here goes through `shellInvoke` / `onShellEvent` in
// `tauri.ts`, the one module that touches the Tauri API, and answers "not
// here" in a browser: a page the daemon serves cannot replace the app.
import { isTauri, onShellEvent, shellInvoke } from "./tauri";

/** Where a check or install is — the shell's `update_state::Phase`. */
type UpdatePhase =
  | "idle"
  | "checking"
  | "upToDate"
  | "available"
  | "downloading"
  | "installing"
  | "failed";

/** The shell's `UpdateStatus` record. */
export interface UpdateStatus {
  /** False in a build made without an update key: it never checks. */
  configured: boolean;
  currentVersion: string;
  phase: UpdatePhase;
  /** Milliseconds since the epoch of the last SUCCESSFUL check. */
  lastCheckedAt: number | null;
  available: { version: string; notes: string | null; date: string | null } | null;
  error: string | null;
  downloaded: number | null;
  total: number | null;
  autoCheck: boolean;
}

/** The event the shell announces every change on. */
const UPDATE_EVENT = "coffer://update";

/** Whether this host can check for and install updates at all. */
export function updatesAvailable(): boolean {
  return isTauri();
}

export function getUpdateStatus(): Promise<UpdateStatus> {
  return shellInvoke<UpdateStatus>("update_status");
}

/** Check now. Resolves with the record the check left, or rejects when a
 *  check could not start (already busy, or a build without an update key). */
export function checkForUpdates(): Promise<UpdateStatus> {
  return shellInvoke<UpdateStatus>("check_for_updates");
}

/** Download, verify and install the update on offer, then relaunch. Resolves
 *  only if the relaunch did not happen — i.e. never on success. */
export function installUpdate(): Promise<void> {
  return shellInvoke<void>("install_update");
}

export function setUpdateAutoCheck(enabled: boolean): Promise<UpdateStatus> {
  return shellInvoke<UpdateStatus>("set_update_auto_check", { enabled });
}

/** Follow the shell's record as it changes; a no-op in a browser. */
export function onUpdateStatus(callback: (status: UpdateStatus) => void): () => void {
  return onShellEvent<UpdateStatus>(UPDATE_EVENT, callback);
}

const AUTO_CHECK_KEY = "coffer.updates.autoCheck";

/** The "Check automatically" choice. It lives in the page's storage, like the
 *  interface language, because the shell keeps no state of its own. */
export function getAutoCheckPreference(): boolean {
  try {
    return localStorage.getItem(AUTO_CHECK_KEY) !== "off";
  } catch {
    return true;
  }
}

export function saveAutoCheckPreference(enabled: boolean): void {
  try {
    localStorage.setItem(AUTO_CHECK_KEY, enabled ? "on" : "off");
  } catch {
    // A page without storage keeps the shell's default (on).
  }
}

/**
 * Tell the shell whether to check automatically, once at startup. The shell's
 * first check waits long enough for this to land.
 */
export function followUpdatePreferenceInShell(
  report: (enabled: boolean) => Promise<unknown> = setUpdateAutoCheck,
): void {
  if (!updatesAvailable()) return;
  report(getAutoCheckPreference()).catch((e: unknown) => {
    console.error("Coffer: could not tell the desktop shell whether to check for updates", e);
  });
}
