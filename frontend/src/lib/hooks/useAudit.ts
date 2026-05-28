// frontend/src/lib/hooks/useAudit.ts
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

type AuditListOut = components["schemas"]["AuditListOut"];

interface UseAuditArgs {
  kind?: string;
  name?: string;
  eventType?: string;
  since?: string;
  limit?: number;
}

export function useAudit(args: UseAuditArgs) {
  const { kind, name, eventType, since, limit = 50 } = args;
  return useQuery({
    queryKey: ["audit", { kind, name, eventType, since, limit }],
    queryFn: async (): Promise<AuditListOut> => {
      const client = getApiClient();
      const query: Record<string, string | number> = { limit };
      if (kind) query.kind = kind;
      if (name) query.name = name;
      if (eventType) query.event_type = eventType;
      if (since) query.since = since;
      const { data, error } = await client.GET("/audit", {
        params: { query: query as never },
      });
      if (error)
        throw new ApiError(
          error.error?.code ?? "INTERNAL_ERROR",
          error.error?.message ?? "list audit failed",
        );
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty audit response");
      return data;
    },
  });
}
