// frontend/src/lib/hooks/useAudit.ts
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

type AuditListOut = components["schemas"]["AuditListOut"];

interface UseAuditArgs {
  kind?: string;
  /** Every event whose type starts with this — a feature's whole trail,
   *  which a kind filter cannot express when its acts span two kinds. */
  eventPrefix?: string;
  name?: string;
  eventType?: string;
  since?: string;
  limit?: number;
  /** False switches the lane off entirely — no request, no discarded response. */
  enabled?: boolean;
}

export function useAudit(args: UseAuditArgs) {
  const { kind, name, eventType, eventPrefix, since, limit = 50, enabled = true } = args;
  return useQuery({
    queryKey: ["audit", { kind, name, eventType, eventPrefix, since, limit }],
    queryFn: async (): Promise<AuditListOut> => {
      const client = getApiClient();
      const query: Record<string, string | number> = { limit };
      if (kind) query.kind = kind;
      if (name) query.name = name;
      if (eventType) query.event_type = eventType;
      if (eventPrefix) query.event_prefix = eventPrefix;
      if (since) query.since = since;
      const { data, error } = await client.GET("/audit", {
        params: { query: query as never },
      });
      if (error) throwApiError(error, "INTERNAL_ERROR", "list audit failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty audit response");
      return data;
    },
    enabled,
  });
}
