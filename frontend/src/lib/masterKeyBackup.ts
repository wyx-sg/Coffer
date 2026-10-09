// src/lib/masterKeyBackup.ts — the backup dialog's one report to the shell.
//
// `coffer secret backup-key` leaves a request the shell keeps open while the
// dialog it opened is (spec secret "Approve from the command line with the
// person's own presence check"). A written backup the shell reports itself,
// from the daemon's answer; closing the dialog is the page's to say. It
// reaches the shell only through the secret supplier (`./tauri`).
import { presenceAvailable, shellInvoke } from "./tauri";

/** The backup dialog closed: a waiting `coffer secret backup-key` ends with nothing written. */
export async function masterKeyBackupClosed(): Promise<void> {
  if (!presenceAvailable()) return;
  // Best effort: a command nobody tells times out on its own.
  await shellInvoke<void>("master_key_backup_closed").catch(() => undefined);
}
