// src/lib/api/retention.ts — request functions for the per-table retention policies and pruning.
import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type { components } from "@/lib/api/types";

export type RetentionPolicyList = components["schemas"]["RetentionPolicyListOut"];
export type RetentionPreview = components["schemas"]["RetentionPreviewOut"];

export const retentionApi = {
  policies: (): Promise<RetentionPolicyList> => unwrap(getApiClient().GET("/retention/policies")),
  update: (tableName: string, retentionDays: number | null): Promise<void> =>
    unwrapVoid(
      getApiClient().PATCH("/retention/policies/{table_name}", {
        params: { path: { table_name: tableName } },
        body: { retention_days: retentionDays },
      }),
    ),
  preview: (tableName: string, days: number): Promise<RetentionPreview> =>
    unwrap(
      getApiClient().GET("/retention/policies/{table_name}/preview", {
        params: { path: { table_name: tableName }, query: { days } },
      }),
    ),
  prune: (tableName?: string) =>
    unwrap(
      getApiClient().POST("/retention/prune", { body: tableName ? { table_name: tableName } : {} }),
    ),
};
