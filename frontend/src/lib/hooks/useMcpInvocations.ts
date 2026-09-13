// frontend/src/lib/hooks/useMcpInvocations.ts
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

type InvocationListOut = components["schemas"]["InvocationListOut"];

export type InvocationStatusFilter = "ok" | "error" | "timeout" | "denied";

interface UseMcpInvocationsArgs {
  serverName: string;
  limit?: number;
  status?: InvocationStatusFilter;
  since?: string;
  enabled?: boolean;
}

export function useMcpInvocations({
  serverName,
  limit = 50,
  status,
  since,
  enabled = true,
}: UseMcpInvocationsArgs) {
  return useQuery({
    queryKey: ["mcp", "invocations", serverName, { limit, status, since }],
    queryFn: async (): Promise<InvocationListOut> => {
      const client = getApiClient();
      const query: Record<string, string | number> = { limit };
      if (status) query.status = status;
      if (since) query.since = since;
      const { data, error } = await client.GET("/resources/mcp_server/{name}/invocations", {
        params: {
          path: { name: serverName },
          query: query as never,
        },
      });
      if (error) throwApiError(error, "INTERNAL_ERROR", "list invocations failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty invocations response");
      return data;
    },
    enabled,
    // Invocation history is append-only audit data, not a live console, so a
    // slower poll suffices.
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });
}
