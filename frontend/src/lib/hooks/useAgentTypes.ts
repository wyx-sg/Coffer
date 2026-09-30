// src/lib/hooks/useAgentTypes.ts — every supported agent type with its detection state, registered or not.
//
// The Overview's first-run panel lists one row per type (spec agent-registry
// "Report every supported type's detection state").
import { useQuery } from "@tanstack/react-query";

import { agentsApi } from "@/lib/api/agents";
import { agentTypesKey } from "@/lib/api/queryKeys";

export function useAgentTypes(enabled = true) {
  return useQuery({
    queryKey: agentTypesKey,
    queryFn: async () => (await agentsApi.types()).types,
    enabled,
  });
}
