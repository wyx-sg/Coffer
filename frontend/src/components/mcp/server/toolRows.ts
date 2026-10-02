// src/components/mcp/server/toolRows.ts — a server's tools as the Overview and Tools tab list them (design 4.1.02, 4.1.06, 4.1.25).
//
// Each tool with its last-24-hours use and, while tiering hides any, whether
// agents see it listed or reach it through search; its input parameters as
// `name · type` chips, and the name agents see.
import type { TFunction } from "i18next";

import type { components } from "@/lib/api/types";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import type { InvocationSummary, ToolTiering } from "@/lib/hooks/useMcpServerPage";
import { CLIENT_NAME_LIMIT } from "../capabilityRows";
import { listingOf, relativeTime, shortTime, usageByTool, type ServerState } from "@/lib/mcp/serverState";

type ToolView = components["schemas"]["MCPToolView"];

/** @ui-only */
export interface ToolRow {
  key: string;
  prefixed: string;
  description: string | null;
  enabled: boolean;
  /** Last-24-hours use; null when there is none to count (off, never answered). */
  calls: number | null;
  errors: number | null;
  lastCallAt: string | null;
  /** "listed" / "behind" while tiering hides some tools; null otherwise. */
  listing: "listed" | "behind" | null;
  params: { name: string; type: string }[];
  /** The name a client shows (`mcp__coffer__<server>__<tool>`) and its length. */
  clientName: string;
  clientNameLength: number;
  tooLong: boolean;
}

function paramsOf(schema: unknown): { name: string; type: string }[] {
  const props = (schema as { properties?: Record<string, unknown> } | null)?.properties;
  if (!props || typeof props !== "object") return [];
  return Object.entries(props).map(([name, p]) => {
    const type = (p as { type?: unknown } | null)?.type;
    return { name, type: Array.isArray(type) ? type.join(" | ") : String(type ?? "any") };
  });
}

export function toolRows(
  tools: readonly ToolView[] | undefined,
  summary: InvocationSummary | undefined,
  tiering: ToolTiering | null | undefined,
  countUsage: boolean,
): ToolRow[] {
  const usage = usageByTool(summary);
  const last = new Map((summary?.by_tool ?? []).map((r) => [r.tool, r.last_call_at ?? null]));
  const listing = listingOf(tiering);
  return (tools ?? []).map((tool) => {
    const use = usage.get(tool.original_name);
    const clientName = `mcp__coffer__${tool.prefixed_name}`;
    return {
      key: tool.original_name,
      prefixed: tool.prefixed_name,
      description: tool.description,
      enabled: tool.enabled,
      calls: countUsage ? (use?.calls ?? 0) : null,
      errors: countUsage ? (use?.errors ?? 0) : null,
      lastCallAt: last.get(tool.original_name) ?? null,
      listing: listing
        ? listing.behind.has(tool.original_name)
          ? "behind"
          : listing.listed.has(tool.original_name)
            ? "listed"
            : null
        : null,
      params: paramsOf(tool.input_schema),
      clientName,
      clientNameLength: tool.client_name_length,
      tooLong: tool.client_name_length > CLIENT_NAME_LIMIT,
    };
  });
}

/** Busiest first; a stable order among tools with the same use. */
export function busiestFirst(rows: readonly ToolRow[]): ToolRow[] {
  return [...rows].sort((a, b) => (b.calls ?? 0) - (a.calls ?? 0));
}

/** Whether a state's last 24 hours say anything about its tools' use. */
export function countsUsage(state: ServerState): boolean {
  return state.kind !== "off" && state.kind !== "launcherMissing";
}

/** Where a list rebuilt from the saved switches came from, in words. */
export function cacheNote(
  t: TFunction,
  state: ServerState,
  detail: McpStatusDetail | null | undefined,
): string {
  const at = detail?.last_ok_at ?? null;
  if (state.kind === "failing")
    return at ? t("mcp.page.fromCacheAt", { at: shortTime(at) }) : t("mcp.page.fromCache");
  return at ? t("mcp.page.listedWhenRan", { ago: relativeTime(at) }) : t("mcp.page.listedSaved");
}
