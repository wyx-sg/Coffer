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

import { agentModelsApi, type AgentModel, type AgentModelsOut } from "@/lib/api/agentModels";
import { agentProviderModelsKey } from "@/lib/api/queryKeys";

function useAgentModelsResponse<T>(agentKey: string, select: (r: AgentModelsOut) => T) {
  return useQuery<AgentModelsOut, Error, T>({
    queryKey: agentProviderModelsKey(agentKey),
    queryFn: () => agentModelsApi.list(agentKey),
    select,
    // The draft agent selector can render before an agent is chosen; an empty
    // key would 404 the endpoint.
    enabled: agentKey !== "",
  });
}

export function useAgentModels(agentKey: string) {
  return useAgentModelsResponse<AgentModel[]>(agentKey, (r) => r.models);
}

/** The model the agent's own config names as its default; null when it names none. */
export function useAgentDefaultModel(agentKey: string) {
  return useAgentModelsResponse<string | null>(agentKey, (r) => r.default_model ?? null);
}
