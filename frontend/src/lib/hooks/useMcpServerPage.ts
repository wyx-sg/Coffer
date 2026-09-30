// src/lib/hooks/useMcpServerPage.ts — the MCP server page's reads beside status (spec mcp-gateway, change revise-web-ui-ia).
//
// The last 24 hours (calls and errors per agent and per tool), the server's own
// log (its stderr and Coffer's start / stop lines) and the tiering split (which
// tools agents see listed, which only through search). Each reads persisted
// state only, so opening a server never spawns it.
import { useQueries, useQuery } from "@tanstack/react-query";

import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import { mcpLogKey, mcpStatusKey, mcpSummaryKey, mcpTieringKey } from "@/lib/api/queryKeys";
import type { components } from "@/lib/api/types";
import { readServerStatus, type McpStatusDetail } from "./useMcpServerStatus";

export type InvocationSummary = components["schemas"]["InvocationSummaryOut"];
export type McpServerLog = components["schemas"]["McpServerLogOut"];
export type ToolTiering = components["schemas"]["ToolTieringOut"];

const path = (uid: string) => ({ params: { path: { uid } } });

/** Calls since 24 hours ago — the page's "Last 24 hours". */
export function useMcpInvocationSummary(uid: string) {
  return useQuery({
    queryKey: mcpSummaryKey(uid),
    enabled: uid.length > 0,
    queryFn: async (): Promise<InvocationSummary> => {
      const { data, error } = await getApiClient().GET(
        "/resources/mcp_server/{uid}/invocations/summary",
        path(uid),
      );
      if (error) throwApiError(error, "INTERNAL_ERROR", "summary failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty summary response");
      return data;
    },
  });
}

/** The newest lines of the server's own log; read only while the drawer shows it. */
export function useMcpServerLog(uid: string, enabled: boolean) {
  return useQuery({
    queryKey: mcpLogKey(uid),
    enabled: enabled && uid.length > 0,
    queryFn: async (): Promise<McpServerLog> => {
      const { data, error } = await getApiClient().GET("/resources/mcp_server/{uid}/log", {
        params: { path: { uid }, query: { limit: 300 } },
      });
      if (error) throwApiError(error, "INTERNAL_ERROR", "log failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty log response");
      return data;
    },
  });
}

/** The tiering split, or null when it could not be read (the list then shows no count). */
async function readToolTiering(uid: string): Promise<ToolTiering | null> {
  const { data, error } = await getApiClient().GET(
    "/resources/mcp_server/{uid}/tiering",
    path(uid),
  );
  return error || !data ? null : data;
}

/** Which of the server's tools are listed to agents and which are behind search. */
export function useMcpToolTiering(uid: string) {
  return useQuery({
    queryKey: mcpTieringKey(uid),
    enabled: uid.length > 0,
    queryFn: () => readToolTiering(uid),
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
      queryFn: () => readToolTiering(uid),
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
