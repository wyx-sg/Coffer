// src/lib/hooks/useSecrets.ts — every query and mutation behind the Secrets page (spec secret).
//
// The list, storing and deleting a value, the plaintext scan and its import,
// and the desktop app's presence-gated reveal. Nothing here ever caches a
// value: the listing carries none, and a revealed one lives only in the
// mutation that fetched it (`gcTime: 0`, reset when the dialog hides it).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useTranslation } from "react-i18next";

import { secretsApi } from "@/lib/api/secret";
import { translateApiError } from "@/lib/api/errors";
import {
  secretScanKey,
  secretsKey,
  secretsListKey,
  pendingApprovalsKey,
} from "@/lib/api/queryKeys";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { revealSecret } from "@/lib/tauri";
import { useToast } from "@/components/ui/toast";

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

/** Where this Mac last handed a secret's value out (the sheet's Recent uses); read while `enabled`. */
export function useSecretUses(ref: string, enabled = true) {
  return useQuery({
    queryKey: [...secretsKey, "uses", ref],
    queryFn: () => secretsApi.uses(ref),
    enabled,
  });
}

/** Add a standalone secret under a minted id. The dialog renders a failure inline. */
export function useAddSecret() {
  const refresh = useRefreshSecrets();
  return useMutation({
    mutationFn: ({ label, value }: { label: string; value: string }) =>
      secretsApi.add(label, value),
    onSuccess: refresh,
  });
}

/** Set (or, empty, remove) a secret's label and/or description. Shown inline by the sheet, so no toast. */
export function useSecretNotes() {
  const refresh = useRefreshSecrets();
  return useMutation({
    mutationFn: ({ ref, ...notes }: { ref: string; label?: string; description?: string }) =>
      secretsApi.setNotes(ref, notes),
    onSuccess: refresh,
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

/** The plaintext secrets found in skills and MCP servers. Read only while `enabled` (the dialog is open). */
export function useSecretScan(enabled: boolean) {
  return useQuery({
    queryKey: secretScanKey,
    queryFn: () => secretsApi.scan(),
    enabled,
    // A scan reads files that change behind Coffer's back: never serve an old one.
    staleTime: 0,
    gcTime: 0,
  });
}

/** Move chosen findings into the store; `dryRun` answers what would move and writes nothing. */
export function useImportSecrets() {
  const qc = useQueryClient();
  const refresh = useRefreshSecrets();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ ids, dryRun }: { ids: string[]; dryRun: boolean }) =>
      secretsApi.importFindings(ids, dryRun),
    onSuccess: (_out, { dryRun }) => {
      if (dryRun) return;
      refresh();
      qc.removeQueries({ queryKey: secretScanKey });
    },
    onError: (e) => toast.error(translateApiError(t, e)),
  });
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
