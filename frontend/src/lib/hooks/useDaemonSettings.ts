// frontend/src/lib/hooks/useDaemonSettings.ts
//
// GET/PUT of the daemon's listening port (spec mcp-gateway FR-028), shaped
// like useCredentialSettings — one query for the current setting, one mutation
// that invalidates it.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { daemonSettingsApi, type DaemonPortSettings } from "@/lib/api/daemonSettings";

/** Shared so the card and its mutation cannot drift apart on the key. */
export const DAEMON_SETTINGS_KEY = ["daemon", "settings"];

export function useDaemonSettings() {
  return useQuery({
    queryKey: DAEMON_SETTINGS_KEY,
    queryFn: (): Promise<DaemonPortSettings> => daemonSettingsApi.get(),
  });
}

export function useUpdateDaemonPort() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (port: number | null): Promise<DaemonPortSettings> =>
      daemonSettingsApi.setPort(port),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: DAEMON_SETTINGS_KEY });
    },
  });
}
