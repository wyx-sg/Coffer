// frontend/src/lib/api/fs.ts — local filesystem browse + open/reveal through
// the loopback daemon (spec agent-registry FR-024/FR-039). A browser can't
// read absolute paths or reach the OS, but the daemon — always on the user's own
// machine — can (ADR daemon-proxies-os-file-actions). `browse` backs the web folder picker; `open`/`reveal`
// back the read-only file viewers' "open in editor" / "reveal in file manager".
//
// Wire types from the agent-registry contract; transport via the shared `call`
// (agents/frontend.md §4).

import { call, enc } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/agent-registry";

type Schemas = components["schemas"];

export type FsEntry = Schemas["FsEntry"];

export type FsBrowseOut = Schemas["FsBrowseOut"];

/** A GUI editor detected as installed (preferred-editor picker, spec ui-shell/004). */
export type EditorOption = Schemas["EditorOption"];

export const fsApi = {
  browse: (path?: string | null): Promise<FsBrowseOut> =>
    call<FsBrowseOut>(`/fs/browse${path ? `?path=${enc(path)}` : ""}`),

  /** Open `path` in the preferred editor (`withApp`) or the OS default app. */
  open: (path: string, withApp?: string): Promise<void> =>
    call<void>("/fs/open", { method: "POST", body: withApp ? { path, with: withApp } : { path } }),

  /** Select / reveal `path` in the OS file manager. */
  reveal: (path: string): Promise<void> =>
    call<void>("/fs/reveal", { method: "POST", body: { path } }),

  /**
   * Open the host's native folder dialog (via the daemon) and return the chosen
   * directory. `available: false` means this host has no native dialog tool, so
   * the caller should fall back to the in-app folder browser; `path: null` with
   * `available: true` means the user cancelled.
   */
  pickFolder: (start?: string | null): Promise<Schemas["FsPickFolderOut"]> =>
    call<Schemas["FsPickFolderOut"]>("/fs/pick-folder", {
      method: "POST",
      body: { start: start ?? null },
    }),

  /** List GUI editors detected as installed, for the preferred-editor picker. */
  listEditors: async (): Promise<EditorOption[]> => {
    const out = await call<Partial<Schemas["FsEditorsOut"]> | null>("/fs/editors");
    return out?.editors ?? [];
  },
};
