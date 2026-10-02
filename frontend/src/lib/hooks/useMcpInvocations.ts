// frontend/src/lib/hooks/useMcpInvocations.ts
import { useQuery } from "@tanstack/react-query";
import { fetchCallPage } from "@/lib/api/activity";
import { mcpServersApi } from "@/lib/api/mcpServers";
import { mcpInvocationsKey } from "@/lib/api/queryKeys";

export type InvocationStatusFilter = "ok" | "error" | "timeout" | "denied";

interface UseMcpInvocationsArgs {
  serverUid: string;
  limit?: number;
  status?: InvocationStatusFilter;
  since?: string;
  enabled?: boolean;
  /** Coffer's own `coffer` server: not a resource, so its calls are read
   *  from the cross-server list (`GET /mcp/invocations?uid=coffer`). */
  builtin?: boolean;
}

export function useMcpInvocations({
  serverUid,
  limit = 50,
  status,
  since,
  enabled = true,
  builtin = false,
}: UseMcpInvocationsArgs) {
  return useQuery({
    queryKey: mcpInvocationsKey(serverUid, { limit, status, since }),
    queryFn: () =>
      builtin
        ? fetchCallPage({ uid: serverUid, status, since }, limit)
        : mcpServersApi.invocations(serverUid, { limit, status, since }),
    enabled,
    // Invocation history is append-only audit data, not a live console, so a
    // slower poll suffices.
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });
}
