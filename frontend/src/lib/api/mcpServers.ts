// src/lib/api/mcpServers.ts — request functions for one registered MCP server's reads and per-capability switches.
import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

export type CapabilityList = components["schemas"]["CapabilityListOut"];
export type McpStatusDetail = components["schemas"]["McpServerStatusOut"];
export type InvocationSummary = components["schemas"]["InvocationSummaryOut"];
export type McpServerLog = components["schemas"]["McpServerLogOut"];
export type ToolTiering = components["schemas"]["ToolTieringOut"];
export type McpTestResult = components["schemas"]["McpTestResultOut"];
export type InvocationList = components["schemas"]["InvocationListOut"];

export type CapabilityType = "tool" | "resource" | "prompt";

/** @ui-only query options the caller passes, not a response; never crosses the wire. */
export interface InvocationFilters {
  limit: number;
  status?: "ok" | "error" | "timeout" | "denied";
  since?: string;
}

/** A read that answers "nothing known" when the daemon refuses it; a transport failure still rejects. */
async function orNull<T>(read: Promise<T>): Promise<T | null> {
  try {
    return await read;
  } catch (e) {
    if (e instanceof ApiError) return null;
    throw e;
  }
}

export const mcpServersApi = {
  capabilities: (uid: string, saved: boolean): Promise<CapabilityList> =>
    unwrap(
      getApiClient().GET("/resources/mcp_server/{uid}/capabilities", {
        params: { path: { uid }, ...(saved ? { query: { saved: true } } : {}) },
      }),
    ),
  setCapabilityEnabled: (
    op: "enable" | "disable",
    uid: string,
    capabilityType: CapabilityType,
    capabilityKey: string,
  ): Promise<void> =>
    unwrapVoid(
      getApiClient().POST(
        `/resources/mcp_server/{uid}/capabilities/{capability_type}/${op}` as
          | "/resources/mcp_server/{uid}/capabilities/{capability_type}/enable"
          | "/resources/mcp_server/{uid}/capabilities/{capability_type}/disable",
        {
          params: { path: { uid, capability_type: capabilityType } },
          body: { capability_key: capabilityKey },
        },
      ),
    ),
  /** The persisted-state status, or null when the daemon refuses the read. */
  status: (uid: string): Promise<McpStatusDetail | null> =>
    orNull(
      unwrap(
        getApiClient().GET("/resources/mcp_server/{uid}/status", { params: { path: { uid } } }),
      ),
    ),
  summary: (uid: string): Promise<InvocationSummary> =>
    unwrap(
      getApiClient().GET("/resources/mcp_server/{uid}/invocations/summary", {
        params: { path: { uid } },
      }),
    ),
  log: (uid: string, limit: number): Promise<McpServerLog> =>
    unwrap(
      getApiClient().GET("/resources/mcp_server/{uid}/log", {
        params: { path: { uid }, query: { limit } },
      }),
    ),
  /** The tiering split, or null when it could not be read. */
  tiering: (uid: string): Promise<ToolTiering | null> =>
    orNull(
      unwrap(
        getApiClient().GET("/resources/mcp_server/{uid}/tiering", { params: { path: { uid } } }),
      ),
    ),
  invocations: (
    uid: string,
    { limit, status, since }: InvocationFilters,
  ): Promise<InvocationList> =>
    unwrap(
      getApiClient().GET("/resources/mcp_server/{uid}/invocations", {
        params: { path: { uid }, query: { limit, status, since } },
      }),
    ),
  /** One test of a registered server: spawn/connect once and report latency. */
  test: (uid: string): Promise<McpTestResult> =>
    unwrap(getApiClient().POST("/resources/mcp_server/{uid}/test", { params: { path: { uid } } })),
};
