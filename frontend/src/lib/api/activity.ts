// src/lib/api/activity.ts — request functions for the three logs Activity reads, each from its owner's route.
//
// The audit log (`GET /audit`) and the MCP invocation log (`GET
// /mcp/invocations`) page newest-first by an opaque cursor and carry `total`,
// the count of every row matching the filters (spec resource-framework "Page
// growing lists by an opaque cursor", "Count a log's matching rows beside
// each page"). The daemon log (`GET /daemon/logs`) pages the same way, by a
// byte offset into the file; its `total` is the matching records of the file's
// recent tail and is only computed when asked for (`withTotal`). Every function
// takes the abort signal of its query, so a stale request is cancelled.
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
  eventType?: string;
  /** Free text, matched by the database. */
  q?: string;
  /** With `q`: event types whose localized wording matched it (composed client-side). */
  qTypes?: string[];
}

/** @ui-only The server-side filters the invocation route takes. */
export interface CallParams {
  since?: string;
  uid?: string;
  /** One outcome, or "failed" for every one but ok (an error, a timeout, a denial). */
  status?: "ok" | "error" | "timeout" | "denied" | "failed";
  agentUid?: string;
  q?: string;
}

/** @ui-only The server-side filters the daemon log route takes. */
export interface DaemonParams {
  since?: string;
  /** Severity floor; "" is every level. */
  level?: string;
  q?: string;
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
  signal?: AbortSignal,
): Promise<AuditListOut> {
  return unwrap(
    getApiClient().GET("/audit", {
      signal,
      params: {
        query: {
          limit,
          since: params.since || undefined,
          kind: params.kind || undefined,
          event_type: params.eventType || undefined,
          q: params.q || undefined,
          q_type: params.q && params.qTypes?.length ? params.qTypes : undefined,
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
  signal?: AbortSignal,
): Promise<InvocationListOut> {
  return unwrap(
    getApiClient().GET("/mcp/invocations", {
      signal,
      params: {
        query: {
          limit,
          since: params.since || undefined,
          uid: params.uid || undefined,
          status: params.status || undefined,
          agent_uid: params.agentUid || undefined,
          q: params.q || undefined,
          cursor: cursor || undefined,
        },
      },
    }),
  );
}

/** One page of the daemon log, newest first; `withTotal` also counts the recent tail. */
export function fetchDaemonPage(
  params: DaemonParams,
  limit: number,
  cursor?: string | null,
  signal?: AbortSignal,
  withTotal = false,
): Promise<DaemonLogListOut> {
  return unwrap(
    getApiClient().GET("/daemon/logs", {
      signal,
      params: {
        query: {
          limit,
          since: params.since || undefined,
          level: params.level || undefined,
          q: params.q || undefined,
          cursor: cursor || undefined,
          with_total: withTotal || undefined,
        },
      },
    }),
  );
}
