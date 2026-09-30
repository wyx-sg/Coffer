// src/lib/api/activity.ts — request functions for the three logs Activity reads, each from its owner's route.
//
// The audit log (`GET /audit`) and the MCP invocation log (`GET
// /mcp/invocations`) page newest-first by an opaque cursor and carry `total`,
// the count of every row matching the filters (spec resource-framework "Page
// growing lists by an opaque cursor", "Count a log's matching rows beside
// each page"). The daemon log (`GET /daemon/logs`) is a bounded tail with no
// cursor: one read is all there is.
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

type AuditListOut = components["schemas"]["AuditListOut"];
type InvocationListOut = components["schemas"]["InvocationListOut"];
type DaemonLogListOut = components["schemas"]["DaemonLogListOut"];

/** The most rows one request may ask any of the three routes for. */
export const MAX_PAGE = 500;

/** @ui-only The server-side filters the audit route takes. */
export interface AuditParams {
  since?: string;
  kind?: string;
}

/** @ui-only The server-side filters the invocation route takes. */
export interface CallParams {
  since?: string;
  uid?: string;
  status?: "ok" | "error" | "timeout" | "denied";
  agentUid?: string;
}

/** @ui-only The server-side filters the daemon log route takes. */
export interface DaemonParams {
  since?: string;
  /** Severity floor; "" is every level. */
  level?: string;
}

/** @ui-only One log and its server-side filters. */
export type SourceParams =
  | { source: "change"; params: AuditParams }
  | { source: "call"; params: CallParams }
  | { source: "daemon"; params: DaemonParams };

export async function fetchAuditPage(
  params: AuditParams,
  limit: number,
  cursor?: string | null,
): Promise<AuditListOut> {
  const query: Record<string, string | number> = { limit };
  if (params.since) query.since = params.since;
  if (params.kind) query.kind = params.kind;
  if (cursor) query.cursor = cursor;
  const { data, error } = await getApiClient().GET("/audit", {
    params: { query: query as never },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "list audit failed");
  if (!data) throw new ApiError("INTERNAL_ERROR", "empty audit response");
  return data;
}

export async function fetchCallPage(
  params: CallParams,
  limit: number,
  cursor?: string | null,
): Promise<InvocationListOut> {
  const query: Record<string, string | number> = { limit };
  if (params.since) query.since = params.since;
  if (params.uid) query.uid = params.uid;
  if (params.status) query.status = params.status;
  if (params.agentUid) query.agent_uid = params.agentUid;
  if (cursor) query.cursor = cursor;
  const { data, error } = await getApiClient().GET("/mcp/invocations", {
    params: { query: query as never },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "list invocations failed");
  if (!data) throw new ApiError("INTERNAL_ERROR", "empty invocations response");
  return data;
}

export async function fetchDaemonTail(
  params: DaemonParams,
  limit: number = MAX_PAGE,
): Promise<DaemonLogListOut> {
  const query: Record<string, string | number> = { limit };
  if (params.since) query.since = params.since;
  if (params.level) query.level = params.level;
  const { data, error } = await getApiClient().GET("/daemon/logs", {
    params: { query: query as never },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "list daemon logs failed");
  if (!data) throw new ApiError("INTERNAL_ERROR", "empty daemon log response");
  return data;
}
