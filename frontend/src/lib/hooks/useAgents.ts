// frontend/src/lib/hooks/useAgents.ts — TanStack Query bindings for agents.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { agentsApi, type AgentCreate, type AgentPatch } from "@/lib/api/agents";

const AGENTS_KEY = ["agents"] as const;

export function useAgents() {
  return useQuery({
    queryKey: AGENTS_KEY,
    queryFn: async () => (await agentsApi.list()).items,
  });
}

export function useRegisterAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AgentCreate) => agentsApi.register(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: AGENTS_KEY });
    },
  });
}

export function usePatchAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { name: string; body: AgentPatch }) => agentsApi.patch(vars.name, vars.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: AGENTS_KEY });
    },
  });
}

export function useRemoveAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => agentsApi.remove(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: AGENTS_KEY });
    },
  });
}

export function useDetectAgents() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => agentsApi.detect(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: AGENTS_KEY });
    },
  });
}
