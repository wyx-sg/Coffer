// frontend/src/lib/hooks/useDaemonLog.ts
//
// The daemon's own log — the third of the records Activity shows, and the
// only one that carries what broke. A record whose line was not JSON comes
// back as `{raw: "<line>"}` (usually a traceback); it is deliberately not
// dropped, so the hook passes the daemon's payload through untouched.
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import { daemonLogsKey } from "@/lib/api/queryKeys";

type DaemonLogListOut = components["schemas"]["DaemonLogListOut"];

interface UseDaemonLogArgs {
  since?: string;
  errorsOnly?: boolean;
  limit?: number;
  /** False switches the lane off entirely — no request, no discarded response. */
  enabled?: boolean;
}

export function useDaemonLog({ since, errorsOnly, limit = 100, enabled = true }: UseDaemonLogArgs) {
  return useQuery({
    queryKey: daemonLogsKey({ since, errorsOnly, limit }),
    queryFn: async (): Promise<DaemonLogListOut> => {
      const client = getApiClient();
      const query: Record<string, string | number | boolean> = { limit };
      if (since) query.since = since;
      if (errorsOnly) query.errors_only = true;
      const { data, error } = await client.GET("/daemon/logs", {
        params: { query: query as never },
      });
      if (error) throwApiError(error, "INTERNAL_ERROR", "list daemon logs failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty daemon log response");
      return data;
    },
    enabled,
  });
}
