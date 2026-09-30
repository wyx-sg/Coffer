// src/lib/hooks/useSecrets.ts — every query and mutation behind the Secrets page (spec credentials).
//
// The list, storing and deleting a value, the plaintext scan and its import,
// and the desktop app's presence-gated reveal. Nothing here ever caches a
// value: the listing carries none, and a revealed one lives only in the
// mutation that fetched it (`gcTime: 0`, reset when the dialog hides it).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { credentialsApi } from "@/lib/api/credentials";
import { translateApiError } from "@/lib/api/errors";
import {
  credentialScanKey,
  credentialsKey,
  credentialsListKey,
  pendingApprovalsKey,
} from "@/lib/api/queryKeys";
import { revealSecret } from "@/lib/tauri";
import { useToast } from "@/components/ui/toast";

/** Every stored and cited ref with what uses it. */
export function useSecrets() {
  return useQuery({ queryKey: credentialsListKey, queryFn: () => credentialsApi.list() });
}

function useRefreshSecrets() {
  const qc = useQueryClient();
  return () => {
    // `credentialsKey` is the prefix of the list and of the approvals; the
    // pending list is named too so a 202 shows its approval at once.
    void qc.invalidateQueries({ queryKey: credentialsKey });
    void qc.invalidateQueries({ queryKey: pendingApprovalsKey });
  };
}

/** Store a value under a ref. Resolves to the approval when the value waits (202). */
export function useSetSecret() {
  const refresh = useRefreshSecrets();
  return useMutation({
    mutationFn: ({ ref, value }: { ref: string; value: string }) => credentialsApi.set(ref, value),
    onSuccess: refresh,
    // No toast: the add and replace dialogs render the failure inline.
  });
}

/** Delete a ref. A `CREDENTIAL_IN_USE` refusal names what still uses it. */
export function useDeleteSecret() {
  const refresh = useRefreshSecrets();
  return useMutation({
    mutationFn: (ref: string) => credentialsApi.remove(ref),
    onSuccess: refresh,
    // No toast: the delete dialog shows the refusal, and who still uses it, inline.
  });
}

/** The plaintext secrets found in files. Read only while `enabled` (the dialog is open). */
export function useSecretScan(enabled: boolean) {
  return useQuery({
    queryKey: credentialScanKey,
    queryFn: () => credentialsApi.scan(),
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
      credentialsApi.importFindings(ids, dryRun),
    onSuccess: (_out, { dryRun }) => {
      if (dryRun) return;
      refresh();
      qc.removeQueries({ queryKey: credentialScanKey });
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
