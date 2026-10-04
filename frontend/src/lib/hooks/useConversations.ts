// frontend/src/lib/hooks/useConversations.ts — the writes on a channel conversation
// (spec chat "Rename and delete a conversation through its agent"): rename it,
// delete it, stop its running turn. The list itself is `useConversationList`.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { chatApi } from "@/lib/api/chat";
import { translateApiError } from "@/lib/api/errors";
import { agentsKey, conversationsKey } from "@/lib/api/queryKeys";

/** Shared onError → toast handler — a failed mutation must never be silent. */
function useToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

/** Both lists show a conversation (the agent's Sessions tab lists its session), so both are read again. */
function useRefreshLists() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: conversationsKey }),
      qc.invalidateQueries({ queryKey: agentsKey }),
    ]);
}

export function useRenameConversation() {
  const refresh = useRefreshLists();
  const onError = useToastError();
  return useMutation({
    mutationFn: (vars: { id: string; title: string }) =>
      chatApi.renameConversation(vars.id, vars.title),
    // Returned, so the row's editor stays until the list shows the new title.
    onSuccess: () => refresh(),
    onError,
  });
}

export function useDeleteConversation() {
  const refresh = useRefreshLists();
  // No onError toast: the confirmation dialog stays open and shows the refusal.
  return useMutation({
    mutationFn: (id: string) => chatApi.deleteConversation(id),
    onSuccess: () => refresh(),
  });
}

export function useInterruptConversation() {
  const refresh = useRefreshLists();
  const onError = useToastError();
  return useMutation({
    mutationFn: (id: string) => chatApi.interruptTurn(id),
    onSuccess: () => refresh(),
    onError,
  });
}
