// frontend/src/lib/hooks/useRetention.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import { retentionKey, retentionPoliciesKey } from "@/lib/api/queryKeys";

type RetentionPolicyListOut = components["schemas"]["RetentionPolicyListOut"];

export function useRetentionPolicies() {
  return useQuery({
    queryKey: retentionPoliciesKey,
    queryFn: async (): Promise<RetentionPolicyListOut> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/retention/policies");
      if (error) throwApiError(error, "INTERNAL_ERROR", "list policies failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty policies response");
      return data;
    },
  });
}

interface UpdatePolicyInput {
  tableName: string;
  retentionDays: number | null;
}

export function useUpdateRetentionPolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ tableName, retentionDays }: UpdatePolicyInput) => {
      const client = getApiClient();
      const { error } = await client.PATCH("/retention/policies/{table_name}", {
        params: { path: { table_name: tableName } },
        body: { retention_days: retentionDays },
      });
      if (error) throwApiError(error, "INTERNAL_ERROR", "update policy failed");
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: retentionKey });
    },
  });
}

type RetentionPreviewOut = components["schemas"]["RetentionPreviewOut"];

/** How many rows a window of `days` would delete from `tableName`; off while `days` is null. */
export function useRetentionPreview(tableName: string, days: number | null) {
  return useQuery({
    queryKey: [...retentionKey, "preview", tableName, days],
    enabled: days !== null,
    queryFn: async (): Promise<RetentionPreviewOut> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/retention/policies/{table_name}/preview", {
        params: { path: { table_name: tableName }, query: { days: days ?? 1 } },
      });
      if (error) throwApiError(error, "INTERNAL_ERROR", "retention preview failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty retention preview");
      return data;
    },
  });
}

export function usePruneNow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (tableName?: string) => {
      const client = getApiClient();
      const { data, error } = await client.POST("/retention/prune", {
        body: tableName ? { table_name: tableName } : {},
      });
      if (error) throwApiError(error, "INTERNAL_ERROR", "prune failed");
      return data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: retentionKey });
    },
  });
}
