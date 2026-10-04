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
  conversationKey,
  conversationsKey as CONVERSATIONS_KEY,
  messagesKey,
  replyFileDiffKey,
  replyFilesKey,
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
    mirror && owed.has(messageId) ? platformName(mirror.platform ?? "") : undefined;
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

/** The files a finished reply changed, as recorded (empty for an older reply). */
export function useReplyFiles(conversationId: string, messageId: string | null, enabled = true) {
  return useQuery({
    queryKey: replyFilesKey(conversationId, messageId ?? ""),
    queryFn: () => chatApi.listReplyFiles(conversationId, messageId!),
    enabled: !!conversationId && !!messageId && enabled,
    staleTime: Infinity,
  });
}

/** One recorded file's unified diff for a reply. */
export function useReplyFileDiff(conversationId: string, messageId: string, path: string) {
  return useQuery({
    queryKey: replyFileDiffKey(conversationId, messageId, path),
    queryFn: () => chatApi.getReplyFileDiff(conversationId, messageId, path),
    staleTime: Infinity,
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
    mutationFn: (body: ConversationCreate) => chatApi.createConversation(body),
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

/** Archive (move to the archived list) or unarchive. Both lists are refreshed. */
function useArchiveMutation(fn: (id: string) => Promise<Conversation>, onDone?: () => void) {
  const qc = useQueryClient();
  const onError = useConversationToastError();
  return useMutation({
    mutationFn: fn,
    onSuccess: (updated: Conversation) => {
      qc.setQueryData(conversationKey(updated.id), updated);
      void qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
      onDone?.();
    },
    onError,
  });
}

export function useArchiveConversation() {
  return useArchiveMutation(chatApi.archiveConversation);
}

export function useUnarchiveConversation() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return useArchiveMutation(chatApi.unarchiveConversation, () =>
    toast.success(t("conversations.history.unarchived")),
  );
}
