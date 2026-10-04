// src/lib/hooks/useSecrets.ts — every query and mutation behind the Secrets page (spec secret).
//
// The list, storing and deleting a value, and the desktop app's presence-gated reveal. Nothing here ever caches a
// value: the listing carries none, and a revealed one lives only in the
// mutation that fetched it (`gcTime: 0`, reset when the dialog hides it).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { secretsApi } from "@/lib/api/secret";
import { secretsKey, secretsListKey, pendingApprovalsKey } from "@/lib/api/queryKeys";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { revealSecret } from "@/lib/tauri";

/** Every stored and cited ref with what uses it; read only while `enabled`. */
export function useSecrets(enabled = true) {
  return useQuery({
    queryKey: secretsListKey,
    queryFn: () => secretsApi.list(),
    enabled,
  });
}

function useRefreshSecrets() {
  const qc = useQueryClient();
  return () => {
    // `secretsKey` is the prefix of the list and of the approvals; the
    // pending list is named too so a 202 shows its approval at once.
    void qc.invalidateQueries({ queryKey: secretsKey });
    void qc.invalidateQueries({ queryKey: pendingApprovalsKey });
  };
}

/** Store a value under a ref. Resolves to the approval when the value waits (202). */
export function useSetSecret() {
  const refresh = useRefreshSecrets();
  return useMutation({
    mutationFn: ({ ref, value }: { ref: string; value: string }) => secretsApi.set(ref, value),
    onSuccess: refresh,
    // No toast: the add and replace dialogs render the failure inline.
  });
}

/** Delete a ref. A `SECRET_IN_USE` refusal names what still uses it. */
export function useDeleteSecret() {
  const refresh = useRefreshSecrets();
  return useMutation({
    mutationFn: (ref: string) => secretsApi.remove(ref),
    onSuccess: refresh,
    // No toast: the delete dialog shows the refusal, and who still uses it, inline.
  });
}

const BULK_DELETE_REFRESH = [secretsKey, pendingApprovalsKey];

/** Delete several refs at once: each is refused or deleted on its own, and one summary toast says how many went. */
export function useBulkDeleteSecrets() {
  const bulk = useBulkMutate({ invalidate: BULK_DELETE_REFRESH });
  return {
    isPending: bulk.isPending,
    run: (refs: string[]) => bulk.run(refs, (ref) => secretsApi.remove(ref)),
  };
}

/** Reveal one value through the desktop app's presence check. Throws outside it. */
export function useRevealSecret() {
  return useMutation({
    mutationFn: (ref: string) => revealSecret(ref),
    // The value must not outlive the dialog showing it.
    gcTime: 0,
    // No toast: a cancelled Touch ID or a refusal is shown in the reveal dialog.
  });
}
