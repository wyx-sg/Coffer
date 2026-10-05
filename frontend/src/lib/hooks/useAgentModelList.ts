// frontend/src/lib/hooks/useAgentModelList.ts — the model catalogue of the agent
// registered under one uid (the channel's default model picker reads it).
//
// The catalogue is keyed by agent TYPE, and a channel stores the agent's uid, so
// the uid is resolved to its type first. Shares the query key of
// useAgentModels, so both hooks answer from one request.
import { useQuery } from "@tanstack/react-query";

import { agentModelsApi, type AgentModel } from "@/lib/api/agentModels";
import { agentProviderModelsKey } from "@/lib/api/queryKeys";
import { useAgent } from "@/lib/hooks/useAgents";

export function useAgentModelList(agentUid: string): AgentModel[] {
  const agentType = useAgent(agentUid).data?.type ?? "";
  const { data } = useQuery({
    queryKey: agentProviderModelsKey(agentType),
    queryFn: () => agentModelsApi.list(agentType),
    enabled: agentType !== "",
  });
  return data?.models ?? [];
}
