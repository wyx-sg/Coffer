// frontend/src/lib/api/agentNativeMemory.ts
// Read-only client for /api/v1/agents/{name}/native-memory — the coding agent's
// OWN native per-project memory stores (Claude Code's
// <config_dir>/projects/<slug>/memory, Codex's global memories/MEMORY.md sliced
// by routed cwd). Coffer never writes them: the UI lists them and opens/reveals
// the directory on disk.
//
// Its own module rather than a section of api/agents.ts, so this surface can
// move independently. Wire types from the agent-registry contract; transport
// via the shared `call` (agents/frontend.md §4).
import { call, enc } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/agent-registry";

/** `memory_dir` is the store's real identity on disk — what open/reveal act on;
 * `path` the real project directory, when Coffer could resolve it. */
export type NativeMemoryStore = components["schemas"]["NativeMemoryStore"];

export type NativeMemoryListOut = components["schemas"]["NativeMemoryListOut"];

export const agentNativeMemoryApi = {
  list: (name: string) => call<NativeMemoryListOut>(`/agents/${enc(name)}/native-memory`),
};
