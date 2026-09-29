// src/lib/hooks/useAgentCounts.ts — one registered agent's counts, from the lists its tabs read.
//
// Every number comes from a query a tab also makes (same key, same cache), so
// the tab bar, the Overview summary rows and the Agents list agree with the
// tables they point at. A kind whose list has not loaded yet is `undefined`,
// never a zero: an unread count is shown as nothing, not as "none".
import { useMemo } from "react";

import {
  hookCounts,
  mcpCounts,
  pluginCounts,
  reachesAgent,
  skillCounts,
  type AgentCounts,
} from "@/lib/agents/counts";
import { useAgentNativeMemory } from "@/lib/hooks/useAgentNativeMemory";
import { useAgentTranscripts } from "@/lib/hooks/useAgentTranscripts";
import {
  useAgentHooks,
  useAgentMcpEntries,
  useAgentPlugins,
  useUnmanagedSkills,
} from "@/lib/hooks/useAgents";
import { useResources } from "@/lib/hooks/useResources";
import { useSkills } from "@/lib/hooks/useSkills";

/** `uid` "" (a type not added) reads nothing and counts nothing. */
export function useAgentCounts(uid: string): AgentCounts {
  const skills = useSkills();
  const unmanaged = useUnmanagedSkills(uid);
  const servers = useResources("mcp_server");
  const entries = useAgentMcpEntries(uid);
  const plugins = useAgentPlugins(uid);
  const hooks = useAgentHooks(uid);
  // One row is enough: the listing's `total` is the whole count.
  const sessions = useAgentTranscripts(uid, { limit: 1 });
  const memory = useAgentNativeMemory(uid);

  return useMemo<AgentCounts>(() => {
    if (!uid) return {};
    const delivered = (skills.data ?? []).filter((s) =>
      (s.bindings ?? []).some((b) => b.agent_uid === uid),
    ).length;
    const cofferServers = servers.data
      ? servers.data.filter((r) => reachesAgent(uid, { enabled: r.enabled, scope: r.scope })).length
      : 0;
    return {
      skills: skills.data ? skillCounts(delivered, unmanaged.data?.items) : undefined,
      mcp: servers.data ? mcpCounts(cofferServers, entries.data?.items) : undefined,
      plugins: pluginCounts(plugins.data?.items),
      hooks: hookCounts(hooks.data),
      sessions: sessions.data?.total,
      memoryStores: memory.data?.items.length,
    };
  }, [
    uid,
    skills.data,
    unmanaged.data,
    servers.data,
    entries.data,
    plugins.data,
    hooks.data,
    sessions.data,
    memory.data,
  ]);
}
