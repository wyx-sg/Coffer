// src/lib/agents/counts.ts — how much of each installed kind an agent has, Coffer's and its own.
//
// The numbers behind the detail page's tab counts, the Overview summary rows
// and the Agents list's Skills / MCP / Plugins columns. Pure: the hook in
// lib/hooks/useAgentCounts.ts feeds it the lists it already reads.
import type { AgentHooksOut, McpEntryOut, PluginOut, UnmanagedSkillOut } from "@/lib/api/agents";
import type { Scope } from "@/lib/hooks/useScope";

export interface OwnerSplit {
  coffer: number;
  own: number;
}

export interface AgentCounts {
  /** Skills Coffer delivers to the agent, and skill folders it has that Coffer does not manage. */
  skills?: OwnerSplit;
  /** MCP servers Coffer serves it through the gateway, and entries directly in its own config. */
  mcp?: OwnerSplit & {
    /** Direct entries that duplicate a registered MCP server (`matches_resource`). */
    duplicates: number;
  };
  plugins?: { total: number; enabled: number; marketplaces: number };
  hooks?: { total: number; coffer: number; files: number };
  /** Transcript sessions on disk. */
  sessions?: number;
  /** Native memory stores. */
  memoryStores?: number;
}

/** Whether a resource with these reach fields reaches the agent `uid` (an unscoped one reaches every agent). */
export function reachesAgent(
  uid: string,
  { enabled, scope }: { enabled: boolean; scope: Scope | null | undefined },
): boolean {
  if (!enabled) return false;
  const agents = scope?.agents ?? null;
  return agents === null || agents.includes(uid);
}

export function skillCounts(
  delivered: number,
  unmanaged: readonly UnmanagedSkillOut[] | undefined,
): OwnerSplit | undefined {
  return unmanaged === undefined ? undefined : { coffer: delivered, own: unmanaged.length };
}

export function mcpCounts(
  cofferServers: number,
  entries: readonly McpEntryOut[] | undefined,
): AgentCounts["mcp"] {
  if (entries === undefined) return undefined;
  const direct = entries.filter((e) => !e.is_coffer);
  return {
    coffer: cofferServers,
    own: direct.length,
    duplicates: direct.filter((e) => e.matches_resource !== null).length,
  };
}

export function pluginCounts(plugins: readonly PluginOut[] | undefined): AgentCounts["plugins"] {
  if (plugins === undefined) return undefined;
  return {
    total: plugins.length,
    enabled: plugins.filter((p) => p.enabled).length,
    marketplaces: new Set(plugins.map((p) => p.marketplace).filter(Boolean)).size,
  };
}

export function hookCounts(hooks: AgentHooksOut | undefined): AgentCounts["hooks"] {
  if (hooks === undefined) return undefined;
  return {
    total: hooks.items.length,
    coffer: hooks.items.filter((h) => h.coffer).length,
    files: new Set(hooks.items.map((h) => h.path)).size,
  };
}
