// frontend/src/lib/hooks/useAskAgain.ts — Ask again on a destination whose secret was refused.
import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { pendingApprovalsKey } from "@/lib/api/queryKeys";
import { secretsApi } from "@/lib/api/secret";
import { useToast } from "@/components/ui/toast";

/**
 * Puts each refused request for the destination `uid` (an MCP server, a
 * provider connection, a channel) back in front of the owner. In the desktop
 * app the request is approved on the spot with Touch ID (the mutation opts in
 * to inline approval); in a browser it waits on the approvals list. `refresh`
 * names the reads that show the destination's state.
 */
export function useAskAgainFor(uid: string, refresh: readonly QueryKey[]) {
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
      for (const queryKey of refresh) void qc.invalidateQueries({ queryKey });
      void qc.invalidateQueries({ queryKey: pendingApprovalsKey });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
