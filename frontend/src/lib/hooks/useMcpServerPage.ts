// src/lib/hooks/useMcpServerPage.ts — the MCP server page's reads beside status (spec mcp-gateway, change revise-web-ui-ia).
//
// The last 24 hours (calls and errors per agent and per tool), the server's own
// log (its stderr and Coffer's start / stop lines) and the tiering split (which
// tools agents see listed, which only through search). Each reads persisted
// state only, so opening a server never spawns it.
import { useQueries, useQuery } from "@tanstack/react-query";

import { mcpServersApi, type InvocationSummary, type ToolTiering } from "@/lib/api/mcpServers";
import { mcpLogKey, mcpStatusKey, mcpSummaryKey, mcpTieringKey } from "@/lib/api/queryKeys";
import { readServerStatus, type McpStatusDetail } from "./useMcpServerStatus";

export type { InvocationSummary, ToolTiering };

/** Calls since 24 hours ago — the page's "Last 24 hours". */
export function useMcpInvocationSummary(uid: string) {
  return useQuery({
    queryKey: mcpSummaryKey(uid),
    enabled: uid.length > 0,
    queryFn: () => mcpServersApi.summary(uid),
  });
}

/** The newest lines of the server's own log; read only while the drawer shows it. */
export function useMcpServerLog(uid: string, enabled: boolean) {
  return useQuery({
    queryKey: mcpLogKey(uid),
    enabled: enabled && uid.length > 0,
    queryFn: () => mcpServersApi.log(uid, 300),
  });
}

/** Which of the server's tools are listed to agents and which are behind search. */
export function useMcpToolTiering(uid: string) {
  return useQuery({
    queryKey: mcpTieringKey(uid),
    enabled: uid.length > 0,
    queryFn: () => mcpServersApi.tiering(uid),
  });
}

/** Every listed server's status and tiering, on the same keys the server pane
 *  reads, so the list's groups and the pane share one cached answer each. */
export function useMcpServerListReads(uids: readonly string[]) {
  const statuses = useQueries({
    queries: uids.map((uid) => ({
      queryKey: mcpStatusKey(uid),
      queryFn: () => readServerStatus(uid),
    })),
  });
  const tierings = useQueries({
    queries: uids.map((uid) => ({
      queryKey: mcpTieringKey(uid),
      queryFn: () => mcpServersApi.tiering(uid),
    })),
  });
  const details = new Map<string, McpStatusDetail | null | undefined>();
  const splits = new Map<string, ToolTiering | null | undefined>();
  uids.forEach((uid, i) => {
    details.set(uid, statuses[i]?.data?.detail);
    splits.set(uid, tierings[i]?.data);
  });
  return { details, splits };
}
