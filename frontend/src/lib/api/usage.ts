// src/lib/api/usage.ts — request functions for /api/v1/usage/*: the metered summary, its CSV, and subscription quota.
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
export type QuotaList = Schemas["QuotaListOut"];
export type AgentQuota = Schemas["AgentQuotaOut"];
export type QuotaWindow = Schemas["QuotaWindowOut"];
export type QuotaRefresh = Schemas["QuotaRefreshOut"];

/** The named ranges the summary resolves in local days. */
export type UsageRangeName = "today" | "7d" | "30d" | "month" | "custom";

/**
 * One summary request: a range (with its inclusive local days when custom) and
 * a grouping.
 * @ui-only — the query string the page builds, not a wire body.
 */
export interface UsageQuery {
  range: UsageRangeName;
  from?: string;
  to?: string;
  group_by: UsageGroupBy;
}

function query(q: UsageQuery) {
  return q.range === "custom"
    ? { range: q.range, from: q.from ?? null, to: q.to ?? null, group_by: q.group_by }
    : { range: q.range, group_by: q.group_by };
}

export async function fetchUsageSummary(q: UsageQuery): Promise<UsageSummary> {
  const { data, error } = await getApiClient().GET("/usage/summary", {
    params: { query: query(q) },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "usage summary failed");
  if (!data) throw new ApiError("INTERNAL_ERROR", "empty usage summary");
  return data;
}

/** The same summary as CSV text. */
export async function fetchUsageCsv(q: UsageQuery): Promise<string> {
  const { data, error } = await getApiClient().GET("/usage/export.csv", {
    params: { query: query(q) },
    parseAs: "text",
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "usage export failed");
  return typeof data === "string" ? data : "";
}

export async function fetchUsageQuota(): Promise<QuotaList> {
  const { data, error } = await getApiClient().GET("/usage/quota");
  if (error) throwApiError(error, "INTERNAL_ERROR", "usage quota failed");
  if (!data) throw new ApiError("INTERNAL_ERROR", "empty usage quota");
  return data;
}

/** Ask Codex's app-server now; `reason` says why nothing was read. */
export async function refreshUsageQuota(): Promise<QuotaRefresh> {
  const { data, error } = await getApiClient().POST("/usage/quota/refresh");
  if (error) throwApiError(error, "INTERNAL_ERROR", "usage quota refresh failed");
  if (!data) throw new ApiError("INTERNAL_ERROR", "empty quota refresh");
  return data;
}
