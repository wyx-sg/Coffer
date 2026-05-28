// frontend/src/lib/hooks/useMcpInvocations.ts
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
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

export type McpServerStatus = "healthy" | "failing";

/**
 * Card-level status of a server — a cheap backend read of persisted
 * state (discovered capabilities + last invocation), no subprocess
 * spawn. `null` = nothing known yet, so the card shows no badge.
 */
export function useMcpServerStatus(serverName: string) {
  return useQuery({
    queryKey: ["mcp", "status", serverName],
    queryFn: async (): Promise<McpServerStatus | null> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/resources/mcp_server/{name}/status", {
        params: { path: { name: serverName } },
      });
      if (error || !data) return null;
      return data.status === "unknown" ? null : data.status;
    },
  });
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
      if (error)
        throw new ApiError(
          error.error?.code ?? "INTERNAL_ERROR",
          error.error?.message ?? "list invocations failed",
        );
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty invocations response");
      return data;
    },
    enabled,
    refetchInterval: 5_000, // poll while viewing
    refetchIntervalInBackground: false,
  });
}
