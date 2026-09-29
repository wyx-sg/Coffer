// frontend/src/lib/hooks/useConversations.ts — TanStack Query bindings for conversations.
import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import {
  chatApi,
  type AgentConfigOut,
  type Conversation,
  type ConversationCreate,
  type Message,
} from "@/lib/api/chat";
import { platformName, undeliveredMessageIds } from "@/lib/chat/mirror";
import {
  agentConfigKey,
  archivedConversationsKey,
  conversationKey,
  conversationsKey as CONVERSATIONS_KEY,
  messagesKey,
} from "@/lib/api/queryKeys";
import { useToast } from "@/components/ui/toast";

/** Shared onError → toast handler — a failed mutation must never be silent. */
function useConversationToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export function useConversations() {
  return useQuery({
    queryKey: CONVERSATIONS_KEY,
    queryFn: async () => (await chatApi.listConversations(false)).conversations,
  });
}

export function useArchivedConversations(enabled = true) {
  return useQuery({
    queryKey: archivedConversationsKey,
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

/**
 * Where a reply typed in this conversation also goes (spec chat "Show where a
 * reply will also be sent"): the mirror (null for a web conversation), and for
 * a message id the platform its channel has not received that message on yet.
 * The listing the page opens a conversation from leaves the mirror out, so a
 * channel conversation reads it from its own GET — the key the send path
 * invalidates when a reply is left pending.
 */
export function useChannelMirror(conversation: Conversation, messages: Message[]) {
  const bound = conversation.channel_binding !== null;
  const detail = useConversation(bound ? conversation.id : "");
  const mirror = bound
    ? (detail.data?.channel_binding?.mirror ?? conversation.channel_binding?.mirror ?? null)
    : null;
  const owed = useMemo(() => undeliveredMessageIds(mirror, messages), [mirror, messages]);
  const notDeliveredTo = (messageId: string) =>
    mirror && owed.has(messageId) ? platformName(mirror.platform) : undefined;
  return { mirror, notDeliveredTo };
}

/**
 * A conversation's managed-agent model (agent_config.model); see the
 * coffer-model-is-an-internal-engine and model-catalogue-read-from-the-agent ADRs.
 */
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

/** Set (or clear) the reasoning effort the conversation's model is run at. */
export function useSetAgentEffort() {
  const qc = useQueryClient();
  const onError = useConversationToastError();
  return useMutation({
    mutationFn: (vars: { id: string; effort: string | null }) =>
      chatApi.setAgentEffort(vars.id, vars.effort),
    onSuccess: (updated: AgentConfigOut, vars) => {
      qc.setQueryData(agentConfigKey(vars.id), updated);
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
