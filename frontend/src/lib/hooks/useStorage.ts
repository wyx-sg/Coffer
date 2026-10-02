// src/lib/hooks/useStorage.ts — Settings › Data's read of what Coffer keeps, and clearing the rebuildable cache.
//
// Spec daemon "Report what Coffer stores and clear the rebuildable cache". The
// clear is confirmed by the caller (ConfirmDialog), which renders a failure
// itself, so the mutation raises no toast; on success it refreshes the sizes
// and the memory pages, whose trees it emptied.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { storageApi, type StorageSummary } from "@/lib/api/storage";
import { memoryKey, storageKey } from "@/lib/api/queryKeys";

export type { StorageSummary };

export function useStorageSummary() {
  return useQuery({
    queryKey: storageKey,
    queryFn: storageApi.summary,
  });
}

export function useClearCache() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: storageApi.clearCache,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: storageKey });
      void qc.invalidateQueries({ queryKey: memoryKey });
    },
  });
}
