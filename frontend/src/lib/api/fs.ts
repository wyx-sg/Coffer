// frontend/src/lib/api/fs.ts — local filesystem browse + open/reveal through
// the loopback daemon (spec 004-agent-registry FR-024/FR-039). A browser can't
// read absolute paths or reach the OS, but the daemon — always on the user's own
// machine — can (ADR-033). `browse` backs the web folder picker; `open`/`reveal`
// back the read-only file viewers' "open in editor" / "reveal in file manager".

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

export interface FsEntry {
  name: string;
  path: string;
}

export interface FsBrowseOut {
  path: string;
  parent: string | null;
  entries: FsEntry[];
}

/** A GUI editor detected as installed (preferred-editor picker, spec 002/004). */
export interface EditorOption {
  label: string;
  value: string;
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  return {
    "X-Coffer-Token": getCofferToken() ?? "",
    "X-Coffer-Actor": "ui",
    ...extra,
  };
}

async function postAction(path: string, body: Record<string, unknown>): Promise<void> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const data = await r.json().catch(() => null);
    const err = data?.error;
    throw new ApiError(
      err?.code ?? "INTERNAL_ERROR",
      err?.message ?? `request failed: ${r.status}`,
    );
  }
}

export const fsApi = {
  browse: async (path?: string | null): Promise<FsBrowseOut> => {
    const qs = path ? `?path=${encodeURIComponent(path)}` : "";
    const r = await fetch(`${getCofferBaseUrl()}/fs/browse${qs}`, {
      headers: authHeaders(),
    });
    const data = await r.json().catch(() => null);
    if (!r.ok) {
      const err = data?.error;
      throw new ApiError(
        err?.code ?? "INTERNAL_ERROR",
        err?.message ?? `request failed: ${r.status}`,
      );
    }
    return data as FsBrowseOut;
  },

  /** Open `path` in the preferred editor (`withApp`) or the OS default app. */
  open: (path: string, withApp?: string): Promise<void> =>
    postAction("/fs/open", withApp ? { path, with: withApp } : { path }),

  /** Select / reveal `path` in the OS file manager. */
  reveal: (path: string): Promise<void> => postAction("/fs/reveal", { path }),

  /** List GUI editors detected as installed, for the preferred-editor picker. */
  listEditors: async (): Promise<EditorOption[]> => {
    const r = await fetch(`${getCofferBaseUrl()}/fs/editors`, { headers: authHeaders() });
    const data = await r.json().catch(() => null);
    if (!r.ok) {
      const err = data?.error;
      throw new ApiError(
        err?.code ?? "INTERNAL_ERROR",
        err?.message ?? `request failed: ${r.status}`,
      );
    }
    return (data?.editors ?? []) as EditorOption[];
  },
};
