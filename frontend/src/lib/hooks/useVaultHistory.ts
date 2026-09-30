// frontend/src/lib/hooks/useVaultHistory.ts
//
// The queries and the one mutation over the vault's history (spec
// vault-storage "Show, compare and restore any version of a vault file"): a
// file's or folder's versions, the diff one version made to one file, and
// restoring a version — a NEW version naming you, so the restore is itself in
// history and nothing is rewritten. Its first consumer is a skill's History
// tab, which reads its master folder `skills/<name>/`.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { skillsKey, vaultDiffKey, vaultHistoryKey, vaultKey } from "@/lib/api/queryKeys";
import { vaultApi, type VaultRestoreIn } from "@/lib/api/vault";

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

/** What one version did to one file. A version never changes, so its diff is
 *  read once. */
export function useVaultDiff(path: string, version: string) {
  return useQuery({
    queryKey: vaultDiffKey(path, version),
    queryFn: () => vaultApi.diff(path, version),
    staleTime: Infinity,
  });
}

/**
 * Put a version back. On success the vault's history and every skill query
 * (its files, their contents) are refreshed, since a restored skill folder is
 * what the Files tab reads. No error toast: the only caller is a confirm
 * dialog, which shows the refusal in place and stays open.
 */
export function useRestoreVaultVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: VaultRestoreIn) => vaultApi.restore(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: vaultKey });
      void qc.invalidateQueries({ queryKey: skillsKey });
    },
  });
}
