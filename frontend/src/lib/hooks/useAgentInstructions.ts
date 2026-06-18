// frontend/src/lib/hooks/useAgentInstructions.ts — TanStack Query bindings for
// the instructions hub (spec 004 item 1). Split from useAgents.ts for the
// file-size limit.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { agentInstructionsApi } from "@/lib/api/agentInstructions";

const AGENTS_KEY = ["agents"] as const;
const masterInstructionsKey = ["instructions", "master"] as const;
const instructionsStatusKey = (name: string) => ["agents", name, "instructions"] as const;

export function useMasterInstructions() {
  return useQuery({
    queryKey: masterInstructionsKey,
    queryFn: () => agentInstructionsApi.getMaster(),
  });
}

export function useSetMasterInstructions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { content: string; expected_fingerprint?: string }) =>
      agentInstructionsApi.setMaster(vars),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: masterInstructionsKey });
      // Every agent's in_sync depends on the master — refresh all agent queries.
      qc.invalidateQueries({ queryKey: AGENTS_KEY });
    },
  });
}

export function useAgentInstructionsStatus(name: string) {
  return useQuery({
    queryKey: instructionsStatusKey(name),
    queryFn: () => agentInstructionsApi.status(name),
    enabled: !!name,
    // A type without an instructions file returns 422 — don't hammer it.
    retry: false,
  });
}

export function useDeliverInstructions(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (deliver: boolean) =>
      deliver ? agentInstructionsApi.deliver(name) : agentInstructionsApi.remove(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: instructionsStatusKey(name) });
    },
  });
}

export function useAdoptInstructions(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => agentInstructionsApi.adopt(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: masterInstructionsKey });
      qc.invalidateQueries({ queryKey: AGENTS_KEY });
    },
  });
}
