// src/lib/hooks/useDaemonPort.ts — the port of the daemon's next start (spec daemon "Bind a fixed, settable port").
//
// Settings → Daemon reads the configured port beside the one the daemon
// answers on, and saves a new one; a saved port is pending until the daemon
// restarts. A refused port (out of range, held by another program) comes back
// as an ApiError whose code and details the Port row renders in place, so the
// save hook raises no toast of its own.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import { daemonPortKey } from "@/lib/api/queryKeys";
import type { components } from "@/lib/api/types";

export type DaemonPort = components["schemas"]["DaemonPortOut"];

export function useDaemonPort(enabled = true) {
  return useQuery({
    queryKey: daemonPortKey,
    enabled,
    queryFn: async (): Promise<DaemonPort> => {
      const { data, error } = await getApiClient().GET("/daemon/port");
      if (error) throwApiError(error, "INTERNAL_ERROR", "port read failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty port response");
      return data;
    },
  });
}

/** Save the port of the next start. No toast: the Port row shows a refusal beside the field. */
export function useSetDaemonPort() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (port: number): Promise<DaemonPort> => {
      const { data, error } = await getApiClient().PUT("/daemon/port", { body: { port } });
      if (error) throwApiError(error, "INTERNAL_ERROR", "port update failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty port response");
      return data;
    },
    onSuccess: (fresh) => qc.setQueryData(daemonPortKey, fresh),
  });
}
