// frontend/src/lib/filePicker.ts — native FOLDER picker (spec 004 FR-024).
// A browser deliberately refuses to hand a page an absolute path, but naming a
// vault-bundle directory needs one, so the web asks the loopback daemon to open
// the host's native folder dialog. `unavailable` is true only when the host has
// no native dialog tool (or the call errors), so the caller can reveal a
// typed-path fallback.
//
// The open-file / save-file counterparts are gone: a file's CONTENTS can travel
// through the browser itself (`<input type="file">` in, `<a download>` out), so
// they needed no daemon round-trip and no native dialog.
import { fsApi } from "./api/fs";

export interface PickOutcome {
  /** The chosen absolute path, or null when the user cancelled. */
  path: string | null;
  /** True when no native dialog could run; the caller falls back to typing. */
  unavailable: boolean;
}

/**
 * Pick a directory. Used by the vault export/import buttons, which name a
 * bundle directory rather than a file.
 */
export async function pickDirectory(start?: string | null): Promise<PickOutcome> {
  try {
    const res = await fsApi.pickFolder(start ?? undefined);
    return { path: res.path, unavailable: !res.available };
  } catch {
    return { path: null, unavailable: true };
  }
}
