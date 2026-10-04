// frontend/src/lib/api/fs.ts — local filesystem browse + open/reveal through
// the loopback daemon (spec daemon "Browse folders without
// reading files", "Open and reveal existing absolute paths"). A browser can't
// read absolute paths or reach the OS, but the daemon — always on the user's own
// machine — can (ADR daemon-proxies-os-file-actions). `browse` backs the web folder picker; `open`/`reveal`
// back the read-only file viewers' "open in editor" / "reveal in file manager".
//
// Wire types from the daemon contract (where the `/fs/*` routes live);
// transport via the typed client (.agents/frontend.md §4).

import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/daemon";

type Schemas = components["schemas"];

export type FsBrowseOut = Schemas["FsBrowseOut"];

/** A GUI editor detected as installed (preferred-editor picker, spec web-ui "Let the user choose an external editor"). */
export type EditorOption = Schemas["EditorOptionOut"];

/** A terminal detected as installed (preferred-terminal picker, spec web-ui "Let the user choose a terminal"). */
export type TerminalOption = Schemas["TerminalOptionOut"];

/** What starts an agent in a terminal: a session to resume, or a prompt to send (daemon "Open an agent session in a terminal"). */
export type OpenTerminalBody = Schemas["FsTerminalRequest"];

export const fsApi = {
  browse: (path?: string | null): Promise<FsBrowseOut> =>
    unwrap(getApiClient().GET("/fs/browse", { params: { query: path ? { path } : {} } })),

  /** Open `path` in the preferred editor (`withApp`) or the OS default app. */
  open: (path: string, withApp?: string): Promise<void> =>
    unwrapVoid(
      getApiClient().POST("/fs/open", { body: withApp ? { path, with: withApp } : { path } }),
    ),

  /** Select / reveal `path` in the OS file manager. */
  reveal: (path: string): Promise<void> =>
    unwrapVoid(getApiClient().POST("/fs/reveal", { body: { path } })),

  /**
   * Open the host's native folder dialog (via the daemon) and return the chosen
   * directory. `available: false` means this host has no native dialog tool, so
   * the caller should fall back to the in-app folder browser; `path: null` with
   * `available: true` means the user cancelled.
   */
  pickFolder: (start?: string | null): Promise<Schemas["FsPickFolderOut"]> =>
    unwrap(getApiClient().POST("/fs/pick-folder", { body: { start: start ?? null } })),

  /** List GUI editors detected as installed, for the preferred-editor picker. */
  listEditors: async (): Promise<EditorOption[]> => {
    const out = await unwrap(getApiClient().GET("/fs/editors"));
    return out.editors;
  },

  /** List terminals detected as installed, for the preferred-terminal picker. */
  listTerminals: async (): Promise<TerminalOption[]> => {
    const out = await unwrap(getApiClient().GET("/fs/terminals"));
    return out.terminals;
  },

  /** Start an agent's session in a terminal window on this host. */
  openTerminal: (body: OpenTerminalBody): Promise<void> =>
    unwrapVoid(getApiClient().POST("/fs/terminal", { body })),
};
