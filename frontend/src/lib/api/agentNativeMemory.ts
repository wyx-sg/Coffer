// frontend/src/lib/api/agentNativeMemory.ts
// Read-only client for /api/v1/agents/{uid}/native-memory — the coding agent's
// OWN native per-project memory stores (Claude Code's
// <config_dir>/projects/<slug>/memory, Codex's global memories/MEMORY.md sliced
// by routed cwd), plus one store's files: a tree and one file's contents.
// Coffer never writes them; the store's page previews them and offers
// open/reveal for a change that has to be real.
//
// A store is addressed by its `memory_dir` throughout, because that IS its
// identity on disk — the project label and path beside it are best-effort
// decodes, and for Codex several rows legitimately share one directory.
//
// Its own module rather than a section of api/agents.ts, so this surface can
// move independently. Wire types from the agent-registry contract; transport
// via the shared `call` (.agents/frontend.md §4).
import { call, enc } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/agent-registry";

/** `memory_dir` is the store's real identity on disk — what open/reveal act on;
 * `path` the real project directory, when Coffer could resolve it. */
export type NativeMemoryStore = components["schemas"]["NativeMemoryStore"];

export type NativeMemoryListOut = components["schemas"]["NativeMemoryListOut"];

/** One entry in a store's tree. `path` is relative to the store directory. */
export interface NativeMemoryFileNode {
  name: string;
  path: string;
  type: "file" | "dir";
  size: number | null;
  /** A directory whose descendants were clipped at the server's depth bound. */
  truncated: boolean;
  children: NativeMemoryFileNode[];
}

export interface NativeMemoryFileTreeOut {
  root: NativeMemoryFileNode;
}

/** One file's contents. No fingerprint: this surface has no write. */
export interface NativeMemoryFileContent {
  path: string;
  /** Absolute path on disk, so the viewer can open / reveal it. */
  abs_path: string;
  content: string;
  truncated: boolean;
  binary: boolean;
  size: number;
}

export const agentNativeMemoryApi = {
  list: (agentUid: string) => call<NativeMemoryListOut>(`/agents/${enc(agentUid)}/native-memory`),
  files: (agentUid: string, dir: string) =>
    call<NativeMemoryFileTreeOut>(
      `/agents/${enc(agentUid)}/native-memory/files?${new URLSearchParams({ dir })}`,
    ),
  fileContent: (agentUid: string, dir: string, path: string) =>
    call<NativeMemoryFileContent>(
      `/agents/${enc(agentUid)}/native-memory/files/content?${new URLSearchParams({ dir, path })}`,
    ),
};
