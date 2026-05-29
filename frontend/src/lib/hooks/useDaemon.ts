// frontend/src/lib/hooks/useDaemon.ts
import { useMutation, useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

type DaemonStatusOut = components["schemas"]["DaemonStatusOut"];

export function useDaemonStatus() {
  return useQuery({
    queryKey: ["daemon", "status"],
    queryFn: async (): Promise<DaemonStatusOut> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/daemon/status");
      if (error) throwApiError(error, "INTERNAL_ERROR", "status failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty status response");
      return data;
    },
    // Only used for the offline banner — poll slowly and stop while the
    // window is backgrounded to avoid waking the daemon every 5s.
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });
}

export function useDaemonBackup() {
  return useMutation({
    mutationFn: async (path?: string) => {
      const client = getApiClient();
      const { data, error } = await client.POST("/daemon/backup", {
        body: path ? { path } : {},
      });
      if (error) throwApiError(error, "INTERNAL_ERROR", "backup failed");
      return data;
    },
  });
}
