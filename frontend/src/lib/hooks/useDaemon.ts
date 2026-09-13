// frontend/src/lib/hooks/useDaemon.ts
import { useQuery } from "@tanstack/react-query";
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
 * Only the desktop host can be out of step: the app is a build that pairs with
 * a daemon version, and it can find one an earlier app left detached and still
 * listening — reachable, answering, and stale. A browser is served *by*
 * whichever daemon is running, so there is no pairing to check, and the Tauri
 * helper answers "matches" there, leaving this permanently false.
 *
 * Only meaningful once status has loaded, hence the `version` gate.
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
