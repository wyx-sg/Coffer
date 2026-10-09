// frontend/src/lib/shellUninstall.ts — uninstalling Coffer, seen from the page
// (spec web-ui "Offer uninstall on Settings › About").
//
// The shell does the work (spec desktop-app "Uninstall Coffer from the app"):
// the presence check when the data goes too, the daemon's uninstall, the wait
// for the daemon to exit, then the app moves itself to the Trash and quits. The
// page only asks and shows the steps the daemon reported. In a browser there is
// nothing to call: the page shows the command instead.
import { isTauri, shellInvoke } from "./tauri";

/** One step of the daemon's uninstall (`UninstallStepOut`). */
interface UninstallStep {
  key: string;
  outcome: "done" | "nothing" | "failed";
  detail: string;
}

export interface UninstallReport {
  ok: boolean;
  steps: UninstallStep[];
  deletes_data: boolean;
}

/** Whether this host can uninstall Coffer from the page. */
export function uninstallAvailable(): boolean {
  return isTauri();
}

/** Uninstall; resolves with the daemon's steps shortly before the app quits.
 *  Rejects — with the app still running — when the person cancels the
 *  presence check or the daemon refuses. */
export function uninstallCoffer(deleteData: boolean): Promise<UninstallReport> {
  return shellInvoke<UninstallReport>("uninstall_coffer", { deleteData });
}
