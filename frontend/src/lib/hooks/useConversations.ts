// frontend/src/lib/hooks/useConversations.ts — stop the turn running on a channel
// conversation (spec chat "Pause the pending queue on interrupt"). The list and
// the row renames and deletes are `useAllAgentSessions`.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { chatApi } from "@/lib/api/chat";
import { translateApiError } from "@/lib/api/errors";
import { agentsKey, allAgentSessionsKey } from "@/lib/api/queryKeys";

/** `silent`: the caller shows the refusal itself (the busy dialog does, inline). */
export function useInterruptConversation({ silent = false }: { silent?: boolean } = {}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => chatApi.interruptTurn(id),
    // Both lists show a session (the agent's Sessions tab lists its own), so both are read again.
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: allAgentSessionsKey }),
        qc.invalidateQueries({ queryKey: agentsKey }),
      ]),
    onError: silent ? undefined : (error) => toast.error(translateApiError(t, error)),
  });
}
