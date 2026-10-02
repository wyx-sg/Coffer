// frontend/src/lib/hooks/useChannelPairing.ts — the mutations behind a channel's
// "Who can use it": issue a pairing code (to add an owner or re-pair one),
// withdraw it, and remove a paired person. Each refreshes the channel's status,
// which is what the page watches for the people list.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { cancelPairingCode, issuePairingCode, removeChannelPerson } from "@/lib/api/channels";
import { useToast } from "@/components/ui/toast";
import { channelStatusKey } from "@/lib/api/queryKeys";

/** Issue a pairing code; refreshes the status (pending_pairing) on success. Pass
 *  a paired person's `sender_id` to have the claimant replace them; without it
 *  the claimant is added as one more owner. */
export function useIssuePairingCode(uid: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (replaces: string | void) => issuePairingCode(uid, replaces || undefined),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: channelStatusKey(uid) });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Withdraw the outstanding pairing code (Cancel on the code panel). */
export function useCancelPairingCode(uid: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => cancelPairingCode(uid),
    onSuccess: () => void qc.invalidateQueries({ queryKey: channelStatusKey(uid) }),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Remove one paired person; the status refresh drops them from the list. */
export function useRemoveChannelPerson(uid: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (senderId: string) => removeChannelPerson(uid, senderId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: channelStatusKey(uid) }),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
