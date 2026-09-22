// frontend/src/lib/hooks/useDaemon.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import { applyDaemonConnection, daemonVersionMatches, restartDaemon } from "@/lib/tauri";
import type { components } from "@/lib/api/types";
import { daemonStatusKey, daemonVersionSkewKey } from "@/lib/api/queryKeys";

type DaemonStatusOut = components["schemas"]["DaemonStatusOut"];

export function useDaemonStatus() {
  return useQuery({
    queryKey: daemonStatusKey,
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
    queryKey: daemonVersionSkewKey(version),
    enabled: version !== undefined,
    queryFn: async (): Promise<boolean> => {
      if (version === undefined) return false;
      // matches === true → compatible → NOT out of date.
      return !(await daemonVersionMatches(version));
    },
  });
}

/**
 * Restart the daemon from the desktop shell and take over the replacement it
 * hands back. useMutation owns the in-flight / error state and dedups
 * double-clicks. No toast: the offline banner renders the error inline, next
 * to the button that caused it.
 */
export function useRestartDaemon() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      // The daemon mints a fresh token on every start, so the credentials the
      // shell handed over at launch are now revoked. The restart already
      // waited for the replacement to answer and returned its connection, so
      // swap that in before anything refetches — otherwise every request 401s
      // until the app is relaunched.
      //
      // Installing what the restart returned, rather than asking for a
      // connection again, is also what keeps a restart to ONE daemon: the
      // second ask used to arrive before the new daemon had bound a port, and
      // the handshake answers "no daemon running" by spawning one.
      const result = await restartDaemon();
      applyDaemonConnection(result);
      return result;
    },
    // The token changed, so every cached query (not just daemon/status) was
    // fetched with the revoked credentials — refetch the whole cache so the
    // app recovers in place.
    onSuccess: () => qc.invalidateQueries(),
  });
}
