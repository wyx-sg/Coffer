// src/lib/hooks/useDaemonPort.ts — the port of the daemon's next start (spec daemon "Bind a fixed, settable port").
//
// Settings → Daemon reads the configured port beside the one the daemon
// answers on, and saves a new one; a saved port is pending until the daemon
// restarts. A refused port (out of range, held by another program) comes back
// as an ApiError whose code and details the Port row renders in place, so the
// save hook raises no toast of its own.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { daemonApi } from "@/lib/api/daemon";
import { daemonPortKey } from "@/lib/api/queryKeys";

export function useDaemonPort(enabled = true) {
  return useQuery({
    queryKey: daemonPortKey,
    enabled,
    queryFn: daemonApi.port,
  });
}

/** Save the port of the next start. No toast: the Port row shows a refusal beside the field. */
export function useSetDaemonPort() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (port: number) => daemonApi.setPort(port),
    onSuccess: (fresh) => qc.setQueryData(daemonPortKey, fresh),
  });
}
