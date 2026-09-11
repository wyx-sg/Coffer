// frontend/src/lib/hooks/useMcpServerStatus.ts
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";

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

/** The stdio launcher missing on THIS machine (imported server, runner not
 * installed here), if any — rendered as "missing <runner>" with a hint to
 * install it manually. Coffer manages configuration; it does not install
 * software on the user's machine. */
export function useMcpServerRunner(serverName: string) {
  return useQuery({
    queryKey: ["mcp", "runner", serverName],
    queryFn: async () => {
      const client = getApiClient();
      const { data, error } = await client.GET("/resources/mcp_server/{name}/status", {
        params: { path: { name: serverName } },
      });
      if (error || !data) return null;
      return { missingRunner: data.missing_runner ?? null };
    },
  });
}
