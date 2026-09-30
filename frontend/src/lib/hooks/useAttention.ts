// src/lib/hooks/useAttention.ts — the cross-kind "needs you" list (GET /api/v1/attention).
//
// What needs a person now, from every source whose feature is on (spec
// resource-framework "Report what needs a person across every kind"). A page
// that shows it live mounts `useDaemonEvents`: a change in what the list
// reports arrives on the daemon's event stream as a `change` of kind
// `attention`, which invalidates this key. The sidebar's count badges read the
// same query on every page, where no stream may be open, so they pass a slow
// `refetchInterval` (lib/hooks/useAttentionSignals.ts).
import { useQuery } from "@tanstack/react-query";

import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import { attentionKey } from "@/lib/api/queryKeys";
import type { components } from "@/lib/api/types";

export type AttentionReport = components["schemas"]["AttentionOut"];
export type AttentionItem = components["schemas"]["AttentionItemOut"];

interface Options {
  /** Re-read on a timer, for a reader with no event stream of its own. */
  refetchInterval?: number;
}

export function useAttention({ refetchInterval }: Options = {}) {
  return useQuery({
    queryKey: attentionKey,
    refetchInterval,
    refetchIntervalInBackground: false,
    queryFn: async (): Promise<AttentionReport> => {
      const { data, error } = await getApiClient().GET("/attention");
      if (error) throwApiError(error, "INTERNAL_ERROR", "read attention failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty attention response");
      return data;
    },
  });
}
