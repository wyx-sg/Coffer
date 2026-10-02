// frontend/src/lib/hooks/useDaemon.ts
import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import {
  applyDaemonConnection,
  daemonVersionMatches,
  inDesktopShell,
  restartDaemon,
} from "@/lib/tauri";
import { restartFromBrowser } from "@/lib/daemonRestart";
import type { components } from "@/lib/api/types";
import { daemonStatusKey, daemonUpgradeKey, daemonVersionSkewKey } from "@/lib/api/queryKeys";

type DaemonStatusOut = components["schemas"]["DaemonStatusOut"];

export function useDaemonStatus() {
  const query = useQuery({
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
  // A probe that has never answered goes back to `pending` (error cleared)
  // while a retry is in flight, so `isError` would flicker false on every
  // retry: the shell read each one as a recovery and restarted its offline
  // timer, and a daemon that was never up never reached the offline state.
  // The failure stands until an answer replaces it.
  const lastError = useRef<unknown>(null);
  if (query.error) lastError.current = query.error;
  if (query.isSuccess) lastError.current = null;
  const retrying =
    query.isFetching && !query.isSuccess && query.errorUpdatedAt > query.dataUpdatedAt;
  if (!query.isError && retrying) {
    return { ...query, isError: true, error: lastError.current } as unknown as typeof query;
  }
  return query;
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
 * Restart the daemon and take over the replacement. In the desktop shell the
 * shell restarts it and hands the replacement back; in a browser the daemon
 * restarts itself and the page reloads from its successor
 * (`lib/daemonRestart.ts`), so that branch settles only if it fails.
 * useMutation owns the in-flight / error state and dedups double-clicks. No
 * toast: the error renders inline, next to the button that caused it.
 */
export function useRestartDaemon() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      if (!inDesktopShell()) {
        await restartFromBrowser();
        return null;
      }
      // The daemon mints a fresh token on every start, so the secrets the
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
    // fetched with the revoked secrets — refetch the whole cache so the
    // app recovers in place.
    onSuccess: (result) => (result ? qc.invalidateQueries() : undefined),
  });
}

/**
 * The hand-off that upgrades Coffer on this machine the way it was installed
 * (spec daemon "Hand an upgrade of Coffer to an agent") — for Settings › About
 * in a browser, where no control can install an update. Asked only when
 * `enabled`, so the desktop shell, which updates itself, never asks.
 */
export function useUpgradeHandoff(enabled: boolean) {
  return useQuery({
    queryKey: daemonUpgradeKey,
    enabled,
    staleTime: Infinity,
    queryFn: async (): Promise<string> => {
      const { data, error } = await getApiClient().GET("/daemon/upgrade");
      if (error) throwApiError(error, "INTERNAL_ERROR", "upgrade hand-off failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty upgrade response");
      return data.handoff.prompt;
    },
  });
}
