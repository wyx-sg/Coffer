// frontend/src/lib/hooks/useAgentDirectMcpEntries.ts — every registered agent's
// direct MCP entries at once, for the Add server dialog's "Import from your
// agents" and the first-run card (spec agent-registry "Plan an import of
// agents' direct MCP entries").
//
// One query per agent under the same key the agent's MCP servers tab reads
// (`agentMcpEntriesKey`), so the dialog and the tab share one cache entry and
// an import or adoption from either refreshes both.
import { useQueries } from "@tanstack/react-query";

import { agentsApi, type AgentOut } from "@/lib/api/agents";
import type { McpEntryOut } from "@/lib/api/agents-workspace";
import { agentMcpEntriesKey } from "@/lib/api/queryKeys";
import { useAgents } from "@/lib/hooks/useAgents";

/** One agent's direct entries: those Coffer does not serve already. */
interface AgentDirectEntries {
  agent: AgentOut;
  /** Entries in the agent's own config files that bypass Coffer. */
  entries: McpEntryOut[];
  /** Entries that duplicate a server Coffer already has (`matches_resource`). */
  duplicates: McpEntryOut[];
}

export function useAgentDirectMcpEntries() {
  const agents = useAgents();
  const list = agents.data ?? [];
  const results = useQueries({
    queries: list.map((agent) => ({
      queryKey: agentMcpEntriesKey(agent.uid),
      queryFn: () => agentsApi.mcpEntries(agent.uid),
    })),
  });
  const groups: AgentDirectEntries[] = list.map((agent, i) => {
    const items = (results[i]?.data?.items ?? []).filter((e) => !e.is_coffer);
    return {
      agent,
      entries: items.filter((e) => e.matches_resource === null),
      duplicates: items.filter((e) => e.matches_resource !== null),
    };
  });
  return {
    groups,
    /** Entries that importing would bring into Coffer. */
    count: groups.reduce((n, g) => n + g.entries.length, 0),
    isLoading: agents.isLoading || results.some((r) => r.isLoading),
  };
}
