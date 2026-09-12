// frontend/src/lib/hooks/useAgentNativeMemory.ts — TanStack Query binding for
// the agent's OWN native memory stores. Read-only: one query, no mutations, so
// there is nothing to invalidate. The key extends the agent's own key so
// deleting or refetching an agent sweeps this subtree with it.
import { useQuery } from "@tanstack/react-query";

import { agentNativeMemoryApi } from "@/lib/api/agentNativeMemory";

export const agentNativeMemoryKey = (name: string) => ["agents", name, "native-memory"] as const;

export function useAgentNativeMemory(name: string) {
  return useQuery({
    queryKey: agentNativeMemoryKey(name),
    queryFn: () => agentNativeMemoryApi.list(name),
    enabled: !!name,
  });
}
