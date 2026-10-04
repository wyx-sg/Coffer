// frontend/src/lib/hooks/useActivityInvocations.ts
//
// The cross-server half of the MCP invocation log: every server's calls, each
// row naming the server it went to. Kept beside — not inside —
// useMcpInvocations because the two answer different questions: that hook is
// "what did THIS server do", this one is "what did the gateway do", and the
// Activity page's Tool calls tab needs the second without inheriting the
// first's 30s poll.
import { useQuery } from "@tanstack/react-query";
import { fetchCallPage } from "@/lib/api/activity";
import type { InvocationStatusFilter } from "@/lib/hooks/useMcpInvocations";
import { mcpAllInvocationsKey } from "@/lib/api/queryKeys";

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
    queryFn: () => fetchCallPage({ status, since }, limit),
    enabled,
  });
}
