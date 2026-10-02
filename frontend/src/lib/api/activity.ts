// src/lib/api/activity.ts — request functions for the three logs Activity reads, each from its owner's route.
//
// The audit log (`GET /audit`) and the MCP invocation log (`GET
// /mcp/invocations`) page newest-first by an opaque cursor and carry `total`,
// the count of every row matching the filters (spec resource-framework "Page
// growing lists by an opaque cursor", "Count a log's matching rows beside
// each page"). The daemon log (`GET /daemon/logs`) is a bounded tail with no
// cursor: one read is all there is.
import { getApiClient, unwrap } from "@/lib/api/client";
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
  name?: string;
  eventType?: string;
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

export function fetchAuditPage(
  params: AuditParams,
  limit: number,
  cursor?: string | null,
): Promise<AuditListOut> {
  return unwrap(
    getApiClient().GET("/audit", {
      params: {
        query: {
          limit,
          since: params.since || undefined,
          kind: params.kind || undefined,
          name: params.name || undefined,
          event_type: params.eventType || undefined,
          cursor: cursor || undefined,
        },
      },
    }),
  );
}

export function fetchCallPage(
  params: CallParams,
  limit: number,
  cursor?: string | null,
): Promise<InvocationListOut> {
  return unwrap(
    getApiClient().GET("/mcp/invocations", {
      params: {
        query: {
          limit,
          since: params.since || undefined,
          uid: params.uid || undefined,
          status: params.status || undefined,
          agent_uid: params.agentUid || undefined,
          cursor: cursor || undefined,
        },
      },
    }),
  );
}

export function fetchDaemonTail(
  params: DaemonParams,
  limit: number = MAX_PAGE,
): Promise<DaemonLogListOut> {
  return unwrap(
    getApiClient().GET("/daemon/logs", {
      params: {
        query: { limit, since: params.since || undefined, level: params.level || undefined },
      },
    }),
  );
}
