// frontend/src/lib/hooks/useDaemon.ts
import { useMutation, useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import { daemonVersionMatches } from "@/lib/tauri";
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

/**
 * Whether the running daemon is out of date relative to this app build.
 *
 * The desktop app bundles its own daemon, so a version mismatch means the app
 * reused a stale daemon a previous app version left detached and listening
 * (P2: version skew). We compare the daemon's reported `version` against the
 * app's expected version in the Tauri shell (`daemon_version_matches`). Only
 * meaningful inside the desktop app and only once status has loaded; elsewhere
 * it resolves to "not out of date" so the banner stays hidden.
 */
export function useDaemonOutOfDate(version: string | undefined) {
  return useQuery({
    queryKey: ["daemon", "version-skew", version],
    enabled: version !== undefined,
    queryFn: async (): Promise<boolean> => {
      if (version === undefined) return false;
      // matches === true → compatible → NOT out of date.
      return !(await daemonVersionMatches(version));
    },
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
