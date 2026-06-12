// frontend/src/lib/hooks/useConversations.ts — TanStack Query bindings for conversations.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  chatApi,
  type Conversation,
  type ConversationCreate,
  type ConversationPatch,
} from "@/lib/api/chat";

export const CONVERSATIONS_KEY = ["conversations"] as const;

export function conversationKey(id: string) {
  return [...CONVERSATIONS_KEY, id] as const;
}

export function messagesKey(conversationId: string) {
  return ["messages", conversationId] as const;
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export function useConversations() {
  return useQuery({
    queryKey: CONVERSATIONS_KEY,
    queryFn: async () => (await chatApi.listConversations()).conversations,
  });
}

export function useConversation(id: string) {
  return useQuery({
    queryKey: conversationKey(id),
    queryFn: () => chatApi.getConversation(id),
    enabled: !!id,
  });
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export function useCreateConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ConversationCreate | undefined) => chatApi.createConversation(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
  });
}

export function useRenameConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: string; title: string }) =>
      chatApi.updateConversation(vars.id, { title: vars.title }),
    onSuccess: (updated: Conversation) => {
      qc.setQueryData(conversationKey(updated.id), updated);
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
  });
}

export function useSetConversationModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: string; model_id: string | null }) =>
      chatApi.updateConversation(vars.id, { model_id: vars.model_id }),
    onSuccess: (updated: Conversation) => {
      qc.setQueryData(conversationKey(updated.id), updated);
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
  });
}

export function useUpdateConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: string; patch: ConversationPatch }) =>
      chatApi.updateConversation(vars.id, vars.patch),
    onSuccess: (updated: Conversation) => {
      qc.setQueryData(conversationKey(updated.id), updated);
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => chatApi.deleteConversation(id),
    onSuccess: (_data, id) => {
      qc.removeQueries({ queryKey: conversationKey(id) });
      qc.removeQueries({ queryKey: messagesKey(id) });
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
  });
}
