// src/lib/hooks/useAgentTypes.ts — every supported agent type with its detection state, registered or not.
//
// The Overview's first-run panel lists one row per type (spec agent-registry
// "Report every supported type's detection state").
import { useQuery } from "@tanstack/react-query";

import { agentsApi } from "@/lib/api/agents";
import { agentInstallHandoffKey, agentTypesKey } from "@/lib/api/queryKeys";

export function useAgentTypes(enabled = true) {
  return useQuery({
    queryKey: agentTypesKey,
    queryFn: async () => (await agentsApi.types()).types,
    enabled,
  });
}

/** The daemon's prompt that hands installing an agent to the person, while no
 *  supported agent is installed on this machine; `null` once one is. */
export function useAgentInstallHandoff(enabled = true) {
  return useQuery({
    queryKey: agentInstallHandoffKey,
    queryFn: async () => (await agentsApi.types()).install_handoff?.prompt ?? null,
    enabled,
  });
}
