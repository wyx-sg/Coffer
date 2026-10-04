// src/lib/api/usage.ts — request functions for /api/v1/usage/*: the metered summary.
//
// Every wire type is an alias of the provider-switching contract's generated
// schemas; transport is the typed openapi-fetch client (agents/frontend.md §4).
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/generated/provider-switching";

type Schemas = components["schemas"];

export type UsageSummary = Schemas["UsageSummaryOut"];
export type UsageSummaryRow = Schemas["UsageSummaryRowOut"];
export type UsageTotals = Schemas["UsageTotalsOut"];
export type UsageGroupBy = Schemas["GroupBy"];

/** The named ranges the summary resolves in local days. */
export type UsageRangeName = "today" | "24h" | "7d" | "30d" | "month" | "custom";

/**
 * One summary request: a range (with its inclusive local days when custom), a
 * grouping, and the optional agent-type and connection filters.
 * @ui-only — the query string the page builds, not a wire body.
 */
export interface UsageQuery {
  range: UsageRangeName;
  from?: string;
  to?: string;
  group_by: UsageGroupBy;
  agent_type?: string;
  connection_uid?: string;
}

function query(q: UsageQuery) {
  const filters = {
    ...(q.agent_type ? { agent_type: q.agent_type } : {}),
    ...(q.connection_uid ? { connection_uid: q.connection_uid } : {}),
  };
  return q.range === "custom"
    ? { range: q.range, from: q.from ?? null, to: q.to ?? null, group_by: q.group_by, ...filters }
    : { range: q.range, group_by: q.group_by, ...filters };
}

export async function fetchUsageSummary(q: UsageQuery): Promise<UsageSummary> {
  const { data, error } = await getApiClient().GET("/usage/summary", {
    params: { query: query(q) },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "usage summary failed");
  if (!data) throw new ApiError("INTERNAL_ERROR", "empty usage summary");
  return data;
}
