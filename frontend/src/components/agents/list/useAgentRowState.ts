// src/components/agents/list/useAgentRowState.ts — the one state an agent row reads as, from the reads it needs.
//
// Detection comes with the type row; an added agent adds its Coffer
// connection and its enabled flag (a kind-agnostic Resource field). The same
// reads back the list row, the detail header and the row menu, so they agree.
import { agentRowState, type AgentRowState } from "@/lib/agents/rowState";
import type { AgentTypeOut, CofferConnection } from "@/lib/api/agents";
import { useAgentConnection } from "@/lib/hooks/useAgents";
import { useResource } from "@/lib/hooks/useResources";

export interface AgentRowStateRead {
  /** Undefined while the type row itself is not read yet. */
  state: AgentRowState | undefined;
  connection: CofferConnection | undefined;
  enabled: boolean;
}

export function useAgentRowState(row: AgentTypeOut | undefined): AgentRowStateRead {
  const uid = row?.uid ?? "";
  const connection = useAgentConnection(uid).data;
  const enabled = useResource(uid).data?.enabled ?? true;
  return {
    state: row ? agentRowState(row, connection?.state, enabled) : undefined,
    connection,
    enabled,
  };
}
