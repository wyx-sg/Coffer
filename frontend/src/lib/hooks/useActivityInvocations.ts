// frontend/src/lib/hooks/useActivityInvocations.ts
//
// The cross-server half of the MCP invocation log: every server's calls, each
// row naming the server it went to. Kept beside — not inside —
// useMcpInvocations because the two answer different questions: that hook is
// "what did THIS server do", this one is "what did the gateway do", and the
// Activity page's MCP calls tab needs the second without inheriting the
// first's 30s poll.
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import type { InvocationStatusFilter } from "@/lib/hooks/useMcpInvocations";
import { mcpAllInvocationsKey } from "@/lib/api/queryKeys";

type InvocationListOut = components["schemas"]["InvocationListOut"];

interface UseActivityInvocationsArgs {
  limit?: number;
  status?: InvocationStatusFilter;
  since?: string;
  /** False switches the lane off entirely — no request, no discarded response. */
  enabled?: boolean;
}

export function useActivityInvocations({
  limit = 50,
  status,
  since,
  enabled = true,
}: UseActivityInvocationsArgs) {
  return useQuery({
    queryKey: mcpAllInvocationsKey({ limit, status, since }),
    queryFn: async (): Promise<InvocationListOut> => {
      const client = getApiClient();
      const query: Record<string, string | number> = { limit };
      if (status) query.status = status;
      if (since) query.since = since;
      const { data, error } = await client.GET("/mcp/invocations", {
        params: { query: query as never },
      });
      if (error) throwApiError(error, "INTERNAL_ERROR", "list invocations failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty invocations response");
      return data;
    },
    enabled,
  });
}
