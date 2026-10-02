// frontend/src/lib/hooks/useRetention.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { retentionApi } from "@/lib/api/retention";
import { retentionKey, retentionPoliciesKey } from "@/lib/api/queryKeys";

export function useRetentionPolicies() {
  return useQuery({
    queryKey: retentionPoliciesKey,
    queryFn: retentionApi.policies,
  });
}

interface UpdatePolicyInput {
  tableName: string;
  retentionDays: number | null;
}

export function useUpdateRetentionPolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ tableName, retentionDays }: UpdatePolicyInput) =>
      retentionApi.update(tableName, retentionDays),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: retentionKey });
    },
  });
}

/** How many rows a window of `days` would delete from `tableName`; off while `days` is null. */
export function useRetentionPreview(tableName: string, days: number | null) {
  return useQuery({
    queryKey: [...retentionKey, "preview", tableName, days],
    enabled: days !== null,
    queryFn: () => retentionApi.preview(tableName, days ?? 1),
  });
}

export function usePruneNow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tableName?: string) => retentionApi.prune(tableName),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: retentionKey });
    },
  });
}
