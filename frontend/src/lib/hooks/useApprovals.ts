// frontend/src/lib/hooks/useApprovals.ts
//
// The approvals a secret change can wait on (spec secret, secret
// boundary): the pending list, and the two answers to one. Rejecting is a
// plain REST call any surface may make; approving runs a presence check in the
// desktop shell (`approvePending`), which signs the grant and sends the
// request itself, so the page only learns the outcome.
//
// The list is polled, because the approvals sheet mounts it on every page and
// an approval can start waiting while the user is anywhere. Inside the shell
// it is also refreshed the moment the shell announces a new one.
import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { secretsApi } from "@/lib/api/secret";
import { translateApiError } from "@/lib/api/errors";
import {
  secretsKey,
  pendingApprovalsKey,
  refusedApprovalsKey,
  secretBoundaryKey,
} from "@/lib/api/queryKeys";
import { approvePending, onApprovalsEvent } from "@/lib/tauri";
import { useToast } from "@/components/ui/toast";

const POLL_MS = 15_000;

/** The window event that reopens the approvals sheet after it was dismissed. */
export const OPEN_APPROVALS_EVENT = "coffer:open-approvals";

/** Reopen the approvals sheet from anywhere (the Secrets page, Settings › Security). */
export function openApprovalsSheet(): void {
  window.dispatchEvent(new Event(OPEN_APPROVALS_EVENT));
}

/** Whether a secret waits for approval before it goes somewhere new. */
export function useSecretBoundarySettings() {
  return useQuery({
    queryKey: secretBoundaryKey,
    queryFn: () => secretsApi.secretBoundary(),
  });
}

/** Every approval still waiting, refreshed on a timer and on the shell's signal. */
export function usePendingApprovals() {
  const qc = useQueryClient();
  useEffect(
    () =>
      onApprovalsEvent(() => {
        void qc.invalidateQueries({ queryKey: pendingApprovalsKey });
      }),
    [qc],
  );
  return useQuery({
    queryKey: pendingApprovalsKey,
    queryFn: () => secretsApi.pendingApprovals(),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });
}

/** Every refused approval nothing has superseded — what "Ask again" applies to. */
export function useRefusedApprovals() {
  return useQuery({
    queryKey: refusedApprovalsKey,
    queryFn: () => secretsApi.refusedApprovals(),
  });
}

/** Put a refused binding to a person again (spec secret: ask-again). */
export function useAskAgain() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (id: string) => secretsApi.askAgain(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: secretsKey }),
    onError: (e) => toast.error(translateApiError(t, e)),
  });
}

/** Refuse one approval. */
export function useRejectApproval() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (id: string) => secretsApi.rejectApproval(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: secretsKey }),
    onError: (e) => toast.error(translateApiError(t, e)),
  });
}

/** Approve one approval through the desktop shell's presence check. */
export function useApproveApproval() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (id: string) => approvePending(id),
    // Settled, not success: a cancelled Touch ID leaves the approval pending,
    // and a failed apply may still have moved it.
    onSettled: () => void qc.invalidateQueries({ queryKey: secretsKey }),
    onError: (e) => toast.error(translateApiError(t, e)),
  });
}
