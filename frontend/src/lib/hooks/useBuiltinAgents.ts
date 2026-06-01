// frontend/src/lib/hooks/useBuiltinAgents.ts — TanStack Query bindings for the
// built-in agent (kind `builtin_agent`, spec 008 US8). Mutations invalidate both
// this list and the chat target picker (useChatTargets) so the Chat surface
// reflects edits/creates/deletes without a reload.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  builtinAgentsApi,
  type BuiltinAgentConfig,
  type BuiltinAgentCreate,
} from "@/lib/api/builtinAgents";

const BUILTIN_AGENTS_KEY = ["builtinAgents"] as const;
const CHAT_TARGETS_KEY = ["chat", "targets"] as const;

export function useBuiltinAgents() {
  return useQuery({
    queryKey: BUILTIN_AGENTS_KEY,
    queryFn: () => builtinAgentsApi.list(),
  });
}

export function useBuiltinAgent(name: string) {
  return useQuery({
    queryKey: ["builtinAgents", name],
    queryFn: () => builtinAgentsApi.get(name),
    enabled: !!name,
  });
}

function useInvalidateBuiltinAgents() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: BUILTIN_AGENTS_KEY });
    void qc.invalidateQueries({ queryKey: CHAT_TARGETS_KEY });
  };
}

export function useCreateBuiltinAgent() {
  const invalidate = useInvalidateBuiltinAgents();
  return useMutation({
    mutationFn: (body: BuiltinAgentCreate) => builtinAgentsApi.create(body),
    onSuccess: invalidate,
  });
}

export function usePatchBuiltinAgent() {
  const invalidate = useInvalidateBuiltinAgents();
  return useMutation({
    mutationFn: (vars: { name: string; config: BuiltinAgentConfig }) =>
      builtinAgentsApi.patch(vars.name, vars.config),
    onSuccess: invalidate,
  });
}

export function useRemoveBuiltinAgent() {
  const invalidate = useInvalidateBuiltinAgents();
  return useMutation({
    mutationFn: (name: string) => builtinAgentsApi.remove(name),
    onSuccess: invalidate,
  });
}
