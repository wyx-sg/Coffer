// frontend/src/lib/hooks/useChannelAskAgain.ts — the refused-secret banner's
// Ask again on a channel.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { channelStatusKey, pendingApprovalsKey } from "@/lib/api/queryKeys";
import { secretsApi } from "@/lib/api/secret";
import { useToast } from "@/components/ui/toast";

/**
 * The refused-secret banner's Ask again: puts each refused request for this
 * channel's secret back in front of the owner. In the desktop app the request
 * is approved on the spot with Touch ID (the mutation opts in to inline
 * approval); in a browser it waits on the approvals list. The channel starts
 * on its next attempt once it is approved.
 */
export function useAskAgainForChannel(uid: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: async () => {
      const { approvals } = await secretsApi.rejectedApprovalsFor(uid);
      return Promise.all(approvals.map((a) => secretsApi.askAgain(a.id)));
    },
    meta: { secretDestination: () => uid },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: channelStatusKey(uid) });
      void qc.invalidateQueries({ queryKey: pendingApprovalsKey });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
