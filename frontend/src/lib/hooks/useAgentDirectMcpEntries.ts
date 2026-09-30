// frontend/src/lib/hooks/useAgentDirectMcpEntries.ts — every registered agent's
// direct MCP entries at once, for the Add server dialog's "Import from your
// agents" (spec agent-registry "Adopt a direct MCP entry into Coffer").
//
// One query per agent under the same key the agent's MCP servers tab reads
// (`agentMcpEntriesKey`), so the dialog and the tab share one cache entry and
// an adoption from either refreshes both.
import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { agentsApi, type AgentOut, type McpEntryOut } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import { agentMcpEntriesKey, resourcesKey } from "@/lib/api/queryKeys";
import { normaliseServerName } from "@/lib/mcp/pasteParse";
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

/** One entry to adopt, with the agent it sits in. */
export interface AdoptChoice {
  agent: AgentOut;
  entry: McpEntryOut;
}

/** The credential refs a secret-looking key's value moves under — the same
 *  readable address the agent's own adopt dialog prefills. */
function defaultSecretRefs(agentName: string, entry: McpEntryOut): Record<string, string> {
  return Object.fromEntries(
    entry.secret_keys.map((key) => [key, `mcp/${agentName}/${entry.name}/${key}`]),
  );
}

export interface AdoptReport {
  adopted: string[];
  failed: { name: string; message: string }[];
}

/**
 * Adopt the chosen entries one after another through each agent's adopt route
 * (register in Coffer, move secrets to the keychain, then remove the entry from
 * the agent's file, keeping a .bak). The name is normalised to the pattern the
 * daemon registers. Never rejects: each entry lands in `adopted` or `failed`,
 * which the dialog reports. No onError toast — the report is the outcome.
 */
export function useAdoptAgentEntries() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: async (choices: AdoptChoice[]): Promise<AdoptReport> => {
      const report: AdoptReport = { adopted: [], failed: [] };
      for (const { agent, entry } of choices) {
        const name = normaliseServerName(entry.name);
        try {
          const res = await agentsApi.adoptMcpEntry(agent.uid, entry.name, {
            source: entry.source,
            ...(entry.secret_keys.length > 0
              ? { secrets: defaultSecretRefs(agent.name, entry) }
              : {}),
            ...(name !== entry.name ? { new_name: name } : {}),
          });
          report.adopted.push(res.name);
        } catch (e) {
          report.failed.push({ name: entry.name, message: translateApiError(t, e) });
        }
      }
      return report;
    },
    onSettled: (_r, _e, choices) => {
      for (const uid of new Set(choices.map((c) => c.agent.uid))) {
        void qc.invalidateQueries({ queryKey: agentMcpEntriesKey(uid) });
      }
      // The prefix of every resource list, the mcp_server one included.
      void qc.invalidateQueries({ queryKey: resourcesKey });
    },
  });
}
