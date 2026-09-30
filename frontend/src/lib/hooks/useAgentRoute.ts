// src/lib/hooks/useAgentRoute.ts — the agent a page under /agents/:type is about.
//
// Pages are addressed by the agent's type; the REST routes by its uid. This
// hook reads the `:type` segment, finds that type's row in the per-type
// listing (`GET /agents/types`, which carries the uid of a registered one) and
// reads the agent itself. A segment that is not a supported type names no
// agent: the page shows its not-found state.
import { useParams } from "react-router-dom";

import { isAgentType } from "@/lib/agents/routes";
import type { AgentOut, AgentType, AgentTypeOut } from "@/lib/api/agents";
import { useAgent, useAgentTypes } from "@/lib/hooks/useAgents";

export interface AgentRoute {
  /** The type the address names, or null when the segment is not a type. */
  type: AgentType | null;
  /** The type's row: detection state, directories, uid when registered. */
  typeRow: AgentTypeOut | undefined;
  /** The registered agent's uid, "" when the type is not added. */
  uid: string;
  agent: AgentOut | undefined;
  /** Still resolving the type row or the agent. */
  isPending: boolean;
  error: unknown;
  /** The type is supported but no agent of it is registered. */
  notAdded: boolean;
}

export function useAgentRoute(): AgentRoute {
  const { type: param = "" } = useParams<{ type: string }>();
  const byType = isAgentType(param);

  const types = useAgentTypes();
  const typeRow = byType ? types.data?.find((row) => row.type === param) : undefined;
  const uid = typeRow?.uid ?? "";
  const agentQuery = useAgent(uid);

  return {
    type: byType ? param : null,
    typeRow,
    uid,
    agent: uid ? agentQuery.data : undefined,
    isPending: byType && (types.isPending || (uid !== "" && agentQuery.isPending)),
    error: byType ? (types.error ?? agentQuery.error) : null,
    notAdded: byType && !types.isPending && !typeRow?.uid,
  };
}
