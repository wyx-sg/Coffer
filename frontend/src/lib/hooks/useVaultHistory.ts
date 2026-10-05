// frontend/src/lib/hooks/useVaultHistory.ts
//
// The vault history hand-off behind the History… dialog (spec vault-storage
// "Hand restoring an earlier version of a vault file to an agent"): the
// daemon's prompt, `git log` command and absolute path for one vault path and
// an optional time. A read that writes nothing, so it is a query: it is asked
// again when the time changes.
import { useQuery } from "@tanstack/react-query";

import { vaultHistoryHandoffKey } from "@/lib/api/queryKeys";
import { vaultApi } from "@/lib/api/vault";

/** `at` is an ISO time, or null to have the agent ask which version. No retry:
 *  a refused path (a secret) says so in the dialog at once. */
export function useVaultHistoryHandoff(path: string | null, at: string | null, enabled = true) {
  return useQuery({
    queryKey: vaultHistoryHandoffKey(path ?? "", at),
    queryFn: () => vaultApi.historyHandoff(path as string, at),
    enabled: enabled && Boolean(path),
    retry: false,
  });
}
