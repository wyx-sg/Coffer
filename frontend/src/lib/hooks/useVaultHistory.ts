// frontend/src/lib/hooks/useVaultHistory.ts
//
// The queries and the one mutation over the vault's history (spec
// vault-storage "Show and restore any version of a vault file or folder"): a
// file's or folder's versions, a version's diff against the one before it or
// against the path as it is now, and restoring a version — a NEW version naming
// you, so the restore is itself in history and nothing is rewritten. A
// knowledge document's History tab reads `knowledge/<collection>/<file>`, a
// skill's its master folder `skills/<name>/`.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  knowledgeKey,
  skillsKey,
  vaultDiffKey,
  vaultHistoryKey,
  vaultKey,
} from "@/lib/api/queryKeys";
import { vaultApi, type VaultDiffAgainst, type VaultRestoreIn } from "@/lib/api/vault";

/** A file's or folder's versions, newest first. No retry: a history that
 *  cannot be read says so in its tab at once, with its own Retry. */
export function useVaultHistory(path: string | null) {
  return useQuery({
    queryKey: vaultHistoryKey(path ?? ""),
    queryFn: () => vaultApi.history(path as string),
    enabled: Boolean(path),
    retry: false,
  });
}

/** One version's diff. What a version changed never changes, so that read is
 *  kept; a comparison with the current content is read afresh each time. */
export function useVaultDiff(path: string, version: string, against: VaultDiffAgainst) {
  return useQuery({
    queryKey: vaultDiffKey(path, version, against),
    queryFn: () => vaultApi.diff(path, version, against),
    staleTime: against === "previous" ? Infinity : 0,
    retry: false,
  });
}

/**
 * Put a version back. On success the vault's history, the skills and the
 * knowledge documents are read again, since a restored file is what their
 * Files tab and document pane show. No error toast: the only caller is a
 * confirm dialog, which shows the refusal in place and stays open.
 */
export function useRestoreVaultVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: VaultRestoreIn) => vaultApi.restore(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: vaultKey });
      void qc.invalidateQueries({ queryKey: skillsKey });
      void qc.invalidateQueries({ queryKey: knowledgeKey });
    },
  });
}
