// frontend/src/lib/hooks/useConversations.ts — TanStack Query bindings for conversations.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import {
  chatApi,
  type AgentConfigOut,
  type Conversation,
  type ConversationCreate,
  type ConversationPatch,
} from "@/lib/api/chat";
import { useToast } from "@/components/ui/toast";

export const CONVERSATIONS_KEY = ["conversations"] as const;

export function conversationKey(id: string) {
  return [...CONVERSATIONS_KEY, id] as const;
}

export function messagesKey(conversationId: string) {
  return ["messages", conversationId] as const;
}

export function agentConfigKey(conversationId: string) {
  return ["agent-config", conversationId] as const;
}

/** Shared onError → toast handler — a failed mutation must never be silent. */
function useConversationToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export const ARCHIVED_CONVERSATIONS_KEY = [...CONVERSATIONS_KEY, "archived"] as const;

export function useConversations() {
  return useQuery({
    queryKey: CONVERSATIONS_KEY,
    queryFn: async () => (await chatApi.listConversations(false)).conversations,
  });
}

export function useArchivedConversations(enabled = true) {
  return useQuery({
    queryKey: ARCHIVED_CONVERSATIONS_KEY,
    queryFn: async () => (await chatApi.listConversations(true)).conversations,
    enabled,
  });
}

export function useConversation(id: string) {
  return useQuery({
    queryKey: conversationKey(id),
    queryFn: () => chatApi.getConversation(id),
    enabled: !!id,
  });
}

/** A conversation's managed-agent model (agent_config.model); see ADR-024 → ADR-032. */
export function useAgentConfig(id: string, enabled = true) {
  return useQuery({
    queryKey: agentConfigKey(id),
    queryFn: () => chatApi.getAgentConfig(id),
    enabled: !!id && enabled,
  });
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export function useCreateConversation() {
  const qc = useQueryClient();
  // No onError toast here: ChatPage renders a contextual create-error banner
  // next to the draft composer, so a toast would double-surface the same failure.
  return useMutation({
    mutationFn: (body: ConversationCreate | undefined) => chatApi.createConversation(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
  });
}

export function useRenameConversation() {
  const qc = useQueryClient();
  const onError = useConversationToastError();
  return useMutation({
    mutationFn: (vars: { id: string; title: string }) =>
      chatApi.updateConversation(vars.id, { title: vars.title }),
    onSuccess: (updated: Conversation) => {
      qc.setQueryData(conversationKey(updated.id), updated);
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
    onError,
  });
}

export function useSetConversationModel() {
  const qc = useQueryClient();
  const onError = useConversationToastError();
  return useMutation({
    mutationFn: (vars: { id: string; model_id: string | null }) =>
      chatApi.updateConversation(vars.id, { model_id: vars.model_id }),
    onSuccess: (updated: Conversation) => {
      qc.setQueryData(conversationKey(updated.id), updated);
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
    onError,
  });
}

/** Set (or clear) a managed agent's own per-conversation model (agent_config.model). */
export function useSetAgentModel() {
  const qc = useQueryClient();
  const onError = useConversationToastError();
  return useMutation({
    mutationFn: (vars: { id: string; model: string | null }) =>
      chatApi.setAgentModel(vars.id, vars.model),
    onSuccess: (updated: AgentConfigOut, vars) => {
      qc.setQueryData(agentConfigKey(vars.id), updated);
    },
    onError,
  });
}

export function useUpdateConversation() {
  const qc = useQueryClient();
  const onError = useConversationToastError();
  return useMutation({
    mutationFn: (vars: { id: string; patch: ConversationPatch }) =>
      chatApi.updateConversation(vars.id, vars.patch),
    onSuccess: (updated: Conversation) => {
      qc.setQueryData(conversationKey(updated.id), updated);
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
    onError,
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();
  const onError = useConversationToastError();
  return useMutation({
    mutationFn: (id: string) => chatApi.deleteConversation(id),
    onSuccess: (_data, id) => {
      qc.removeQueries({ queryKey: conversationKey(id) });
      qc.removeQueries({ queryKey: messagesKey(id) });
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
    onError,
  });
}

/** Archive (move to the archived list) or restore. Both lists are refreshed. */
function useArchiveMutation(fn: (id: string) => Promise<Conversation>) {
  const qc = useQueryClient();
  const onError = useConversationToastError();
  return useMutation({
    mutationFn: fn,
    onSuccess: (updated: Conversation) => {
      qc.setQueryData(conversationKey(updated.id), updated);
      void qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
    onError,
  });
}

export function useArchiveConversation() {
  return useArchiveMutation(chatApi.archiveConversation);
}

export function useUnarchiveConversation() {
  return useArchiveMutation(chatApi.unarchiveConversation);
}
