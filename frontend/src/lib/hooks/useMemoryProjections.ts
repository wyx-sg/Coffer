// frontend/src/lib/hooks/useMemoryProjections.ts
//
// TanStack Query bindings for memory stores + their per-agent projections
// (spec 007). The agent detail page uses these to list each memory store's
// projection status for an agent and establish/remove it.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  establishProjection,
  listMemoryStores,
  listProjections,
  removeProjection,
} from "@/kinds/memory/api";

export function useMemoryStores() {
  return useQuery({
    queryKey: ["memory-stores"],
    queryFn: async () => (await listMemoryStores()).memory_stores,
  });
}

export function useMemoryProjections(store: string) {
  return useQuery({
    queryKey: ["memory-projections", store],
    queryFn: async () => (await listProjections(store)).projections,
    enabled: Boolean(store),
  });
}

export function useEstablishProjection(store: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { agentRef: string; projectRoot?: string | null }) =>
      establishProjection(store, vars.agentRef, vars.projectRoot),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["memory-projections", store] });
    },
  });
}

export function useRemoveProjection(store: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (agentRef: string) => removeProjection(store, agentRef),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["memory-projections", store] });
    },
  });
}
