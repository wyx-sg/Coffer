// frontend/src/lib/hooks/useAgentModels.ts — TanStack Query binding for an
// agent's model catalogue (/agent-providers/{key}/models).
//
// What the route answers is what a picker should OFFER. On the agent's own
// built-in login that is the agent's own catalogue, read back from the installed
// agent rather than held as a frontend constant that drifts. With a Coffer
// connection projected into this agent, its curated ids are the list instead —
// the turns go to that endpoint, so the agent's own names would be rejected.
// The narrowing happens once, in the daemon: this hook adds nothing to the
// answer and the picker unions nothing into it, which is what keeps the web
// picker and a channel's `/model` card giving the same answer.
import { useQuery } from "@tanstack/react-query";

import { agentModelsApi, type AgentModel } from "@/lib/api/agentModels";
import { agentProviderModelsKey } from "@/lib/api/queryKeys";

export function useAgentModels(agentKey: string) {
  return useQuery<AgentModel[]>({
    queryKey: agentProviderModelsKey(agentKey),
    queryFn: async () => (await agentModelsApi.list(agentKey)).models,
    // The draft agent selector can render before an agent is chosen; an empty
    // key would 404 the endpoint.
    enabled: agentKey !== "",
  });
}
