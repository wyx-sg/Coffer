// src/lib/hooks/useStorage.ts — Settings › Data's read of what Coffer keeps.
//
// Spec daemon "Report what Coffer stores": the vault, local content and
// history sizes behind Settings › Data.
import { useQuery } from "@tanstack/react-query";

import { storageApi, type StorageSummary } from "@/lib/api/storage";
import { storageKey } from "@/lib/api/queryKeys";

export type { StorageSummary };

export function useStorageSummary() {
  return useQuery({
    queryKey: storageKey,
    queryFn: storageApi.summary,
  });
}
