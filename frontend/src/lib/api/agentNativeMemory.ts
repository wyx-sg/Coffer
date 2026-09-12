// frontend/src/lib/api/agentNativeMemory.ts
// Read-only client for /api/v1/agents/{name}/native-memory — the coding agent's
// OWN native per-project memory stores (Claude Code's
// <config_dir>/projects/<slug>/memory, Codex's global memories/MEMORY.md sliced
// by routed cwd). Coffer never writes them: the UI lists them and opens/reveals
// the directory on disk.
//
// Its own module rather than a section of api/agents.ts, so this surface can
// move independently; the transport helpers are reused from there (§4 of
// agents/frontend.md — one call<T>(), not a fifth copy).
import { call, enc } from "./agents";

export interface NativeMemoryStore {
  /** Best-effort project label (the leaf of the resolved project path). */
  project: string;
  /** The real project directory, when Coffer could resolve it. */
  path: string | null;
  /** The store's real identity on disk — what open/reveal act on. */
  memory_dir: string;
  item_count: number;
}

export interface NativeMemoryListOut {
  items: NativeMemoryStore[];
}

export const agentNativeMemoryApi = {
  list: (name: string) => call<NativeMemoryListOut>("GET", `/agents/${enc(name)}/native-memory`),
};
