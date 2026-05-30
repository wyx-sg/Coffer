// frontend/src/lib/api/fs.ts — read-only local filesystem browse for the
// web folder picker (spec 004-agent-registry FR-024). A browser can't read
// absolute paths, but the loopback daemon can — so the web folder picker
// navigates the filesystem through the daemon and hands back a real path.

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

export const fsApi = {
  browse: async (path?: string | null): Promise<FsBrowseOut> => {
    const qs = path ? `?path=${encodeURIComponent(path)}` : "";
    const r = await fetch(`${getCofferBaseUrl()}/fs/browse${qs}`, {
      headers: {
        "X-Coffer-Token": getCofferToken() ?? "",
        "X-Coffer-Actor": "ui",
      },
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
};
