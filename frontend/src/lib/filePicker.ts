// frontend/src/lib/filePicker.ts — native open-file / save-file dialogs
// (spec 004 FR-042, ADR-036). Mirrors FolderPicker's hybrid strategy: the
// packaged desktop app uses the Tauri OS-native dialog; the web asks the
// loopback daemon to open the host's native dialog. `unavailable` is true only
// when the host has no native dialog tool (or the call errors), so the caller
// can reveal a typed-path fallback — there is no in-app file browser the way
// there is for folders.
import { fsApi } from "./api/fs";
import { isTauri } from "./tauri";

export interface PickOutcome {
  /** The chosen absolute path, or null when the user cancelled. */
  path: string | null;
  /** True when no native dialog could run; the caller falls back to typing. */
  unavailable: boolean;
}

/**
 * Open the Tauri OS-native dialog. A static import specifier lets Vite bundle
 * the plugin so it resolves in the packaged app (see FolderPicker for the
 * rationale); `isTauri()` guards invocation on the web.
 */
async function tauriDialog(
  kind: "open" | "save",
  options: { defaultPath?: string },
): Promise<string | null> {
  const dialog = await import("@tauri-apps/plugin-dialog");
  if (kind === "open") {
    const picked = await dialog.open({ multiple: false, directory: false, ...options });
    return typeof picked === "string" ? picked : null;
  }
  const picked = await dialog.save(options);
  return typeof picked === "string" ? picked : null;
}

/** Pick an existing file to open. */
export async function pickOpenFile(start?: string | null): Promise<PickOutcome> {
  if (isTauri()) {
    try {
      return {
        path: await tauriDialog("open", { defaultPath: start ?? undefined }),
        unavailable: false,
      };
    } catch {
      return { path: null, unavailable: true };
    }
  }
  try {
    const res = await fsApi.pickFile(start ?? undefined);
    return { path: res.path, unavailable: !res.available };
  } catch {
    return { path: null, unavailable: true };
  }
}

/** Pick a destination to save a file to, pre-filled with `suggestedName`. */
export async function pickSaveFile(
  suggestedName: string,
  start?: string | null,
): Promise<PickOutcome> {
  if (isTauri()) {
    const defaultPath = start ? `${start.replace(/\/$/, "")}/${suggestedName}` : suggestedName;
    try {
      return { path: await tauriDialog("save", { defaultPath }), unavailable: false };
    } catch {
      return { path: null, unavailable: true };
    }
  }
  try {
    const res = await fsApi.saveFile(suggestedName, start ?? undefined);
    return { path: res.path, unavailable: !res.available };
  } catch {
    return { path: null, unavailable: true };
  }
}
