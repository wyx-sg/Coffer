// src/lib/hooks/useAgentRoute.ts — the agent a page under /agents/:type is about.
//
// Pages are addressed by the agent's type; the REST routes by its uid. This
// hook reads the `:type` segment, finds that type's row in the per-type
// listing (`GET /agents/types`, which carries the uid of a registered one) and
// reads the agent itself. It also keeps old addresses working: a `:type`
// segment that is really an agent's uid (every link before the rebuild) is
// replaced by the agent's type with the rest of the address kept, and the old
// tab forms (`?tab=mcpServers`, `/conversations?path=`, `/memory?dir=`) are
// replaced by today's (lib/agents/routes.ts `legacyAgentPath`).
import { useEffect } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { agentBasePath, isAgentType, legacyAgentPath } from "@/lib/agents/routes";
import type { AgentOut, AgentType, AgentTypeOut } from "@/lib/api/agents";
import { useAgent, useAgentTypes } from "@/lib/hooks/useAgents";

export interface AgentRoute {
  /** The type the address names, or null while an old uid address redirects. */
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
  /** The address is being replaced by its current form. */
  redirecting: boolean;
}

export function useAgentRoute(): AgentRoute {
  const { type: param = "" } = useParams<{ type: string }>();
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const byType = isAgentType(param);

  const types = useAgentTypes();
  const typeRow = byType ? types.data?.find((row) => row.type === param) : undefined;
  // An old address names the agent by uid; read it to learn its type.
  const uid = byType ? (typeRow?.uid ?? "") : param;
  const agentQuery = useAgent(uid);
  const agent = agentQuery.data;

  const base = agentBasePath(param);
  const rest = pathname.startsWith(base) ? pathname.slice(base.length) : "";
  let target: string | null = null;
  if (!byType && agent) {
    const current = `${agentBasePath(agent.type)}${rest}`;
    target = legacyAgentPath(agent.type, rest, search) ?? `${current}${search}`;
  } else if (byType) {
    target = legacyAgentPath(param, rest, search);
  }
  useEffect(() => {
    if (target !== null) navigate(target, { replace: true });
  }, [target, navigate]);

  const typePending = byType && types.isPending;
  const agentPending = uid !== "" && agentQuery.isPending;
  return {
    type: byType ? param : null,
    typeRow,
    uid: byType ? uid : "",
    agent: byType ? agent : undefined,
    isPending: typePending || agentPending || (!byType && !agentQuery.error),
    error: byType ? (types.error ?? agentQuery.error) : agentQuery.error,
    notAdded: byType && !types.isPending && !typeRow?.uid,
    redirecting: target !== null,
  };
}
