// frontend/src/lib/filePicker.ts — native open-file / save-file dialogs
// (spec 004 FR-042, ADR-036). Mirrors FolderPicker's strategy: the web asks the
// loopback daemon to open the host's native dialog. `unavailable` is true only
// when the host has no native dialog tool (or the call errors), so the caller
// can reveal a typed-path fallback — there is no in-app file browser the way
// there is for folders.
import { fsApi } from "./api/fs";

export interface PickOutcome {
  /** The chosen absolute path, or null when the user cancelled. */
  path: string | null;
  /** True when no native dialog could run; the caller falls back to typing. */
  unavailable: boolean;
}

/** Pick an existing file to open. */
export async function pickOpenFile(start?: string | null): Promise<PickOutcome> {
  try {
    const res = await fsApi.pickFile(start ?? undefined);
    return { path: res.path, unavailable: !res.available };
  } catch {
    return { path: null, unavailable: true };
  }
}

/**
 * Pick a directory. Used by the vault export/import buttons, which name a
 * bundle directory rather than a file. Same `unavailable` semantics as
 * `pickOpenFile`: the caller reveals a typed-path fallback.
 */
export async function pickDirectory(start?: string | null): Promise<PickOutcome> {
  try {
    const res = await fsApi.pickFolder(start ?? undefined);
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
  try {
    const res = await fsApi.saveFile(suggestedName, start ?? undefined);
    return { path: res.path, unavailable: !res.available };
  } catch {
    return { path: null, unavailable: true };
  }
}
