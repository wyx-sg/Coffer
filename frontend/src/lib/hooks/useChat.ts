// frontend/src/lib/hooks/useChat.ts — TanStack Query bindings for chat
// conversations (spec 008-builtin-agent-chat). The message stream itself is
// driven imperatively by the ChatConversation component (see streamMessage in
// lib/api/chat.ts), so it is not modelled as a query here.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import {
  chatApi,
  type ConversationStatus,
  type CreateConversationIn,
  type RenameConversationIn,
} from "@/lib/api/chat";
import { useToast } from "@/components/ui/toast";

const CONVERSATIONS_KEY = ["conversations"] as const;

const conversationKey = (id: string) => ["conversations", id] as const;
const listKey = (status?: ConversationStatus) => ["conversations", { status }] as const;

/** Shared onError → toast handler for the single-use chat mutations. */
function useChatToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

export function useConversations(status?: ConversationStatus) {
  return useQuery({
    queryKey: listKey(status),
    queryFn: async () => (await chatApi.list(status)).items,
  });
}

export function useConversation(id: string) {
  return useQuery({
    queryKey: conversationKey(id),
    queryFn: () => chatApi.get(id),
    enabled: !!id,
  });
}

export function useCreateConversation() {
  const qc = useQueryClient();
  const onError = useChatToastError();
  return useMutation({
    mutationFn: (body: CreateConversationIn) => chatApi.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
    onError,
  });
}

export function useRenameConversation() {
  const qc = useQueryClient();
  const onError = useChatToastError();
  return useMutation({
    mutationFn: (vars: { id: string; body: RenameConversationIn }) =>
      chatApi.rename(vars.id, vars.body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
      qc.invalidateQueries({ queryKey: conversationKey(vars.id) });
    },
    onError,
  });
}

export function useArchiveConversation() {
  const qc = useQueryClient();
  const onError = useChatToastError();
  return useMutation({
    mutationFn: (id: string) => chatApi.archive(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
      qc.invalidateQueries({ queryKey: conversationKey(id) });
    },
    onError,
  });
}

export function useRestoreConversation() {
  const qc = useQueryClient();
  const onError = useChatToastError();
  return useMutation({
    mutationFn: (id: string) => chatApi.restore(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
      qc.invalidateQueries({ queryKey: conversationKey(id) });
    },
    onError,
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();
  const onError = useChatToastError();
  return useMutation({
    mutationFn: (id: string) => chatApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
    onError,
  });
}
