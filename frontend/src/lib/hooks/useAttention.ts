// src/lib/hooks/useAttention.ts — the cross-kind "needs you" list (GET /api/v1/attention).
//
// What needs a person now, from every source whose feature is on (spec
// resource-framework "Report what needs a person across every kind"). No
// poll: a change in what the list reports arrives on the daemon's event
// stream as a `change` of kind `attention`, and `useDaemonEvents` invalidates
// this key.
import { useQuery } from "@tanstack/react-query";

import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import { attentionKey } from "@/lib/api/queryKeys";
import type { components } from "@/lib/api/types";

export type AttentionReport = components["schemas"]["AttentionOut"];
export type AttentionItem = components["schemas"]["AttentionItemOut"];

export function useAttention() {
  return useQuery({
    queryKey: attentionKey,
    queryFn: async (): Promise<AttentionReport> => {
      const { data, error } = await getApiClient().GET("/attention");
      if (error) throwApiError(error, "INTERNAL_ERROR", "read attention failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty attention response");
      return data;
    },
  });
}
