// src/components/mcp/server/McpToolsTab.tsx — the open server's Tools tab: All tools · N of M on, Search tools, All on · All off, the table (design 4.1.25, 4.1.06).
//
// The same table as the Overview's, every tool in the server's own order and
// the first TAB_SHOWN of them, with the filter finding the rest. A list rebuilt
// from the saved switches (the server could not be reached) says so: the
// switches still apply when it answers.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { SearchInput } from "@/components/SearchInput";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { mcpCapabilitiesKey, mcpTieringKey } from "@/lib/api/queryKeys";
import type { components } from "@/lib/api/types";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { capabilitiesApi } from "@/lib/hooks/useMcpCapabilityMutations";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import type { InvocationSummary, ToolTiering } from "@/lib/hooks/useMcpServerPage";
import { McpToolTable } from "./McpToolTable";
import { NoTools } from "./McpTopTools";
import type { ServerState } from "./serverState";
import { cacheNote, countsUsage, toolRows } from "./toolRows";

type CapabilityListOut = components["schemas"]["CapabilityListOut"];

/** How many rows the tab lists before "Filter to find the rest". */
const TAB_SHOWN = 10;

interface Props {
  serverUid: string;
  state: ServerState;
  detail: McpStatusDetail | null | undefined;
  capabilities: CapabilityListOut | undefined;
  pending: boolean;
  error: unknown;
  summary: InvocationSummary | undefined;
  tiering: ToolTiering | null | undefined;
}

export function McpToolsTab({
  serverUid,
  state,
  detail,
  capabilities,
  pending,
  error,
  summary,
  tiering,
}: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const bulk = useBulkMutate({
    invalidate: [mcpCapabilitiesKey(serverUid), mcpTieringKey(serverUid)],
  });
  const tools = capabilities?.tools ?? [];
  const rows = toolRows(tools, summary, tiering, countsUsage(state));
  const on = rows.filter((r) => r.enabled).length;
  const q = query.trim().toLowerCase();
  const matching = q
    ? rows.filter((r) => `${r.key} ${r.description ?? ""}`.toLowerCase().includes(q))
    : rows;
  const fromCache = capabilities?.from_cache ?? false;

  const setAll = (op: "enable" | "disable") =>
    void bulk.run(
      tools.filter((tool) => tool.enabled !== (op === "enable")),
      (tool) =>
        capabilitiesApi.setEnabled(op, {
          serverUid,
          capabilityType: "tool",
          capabilityKey: tool.original_name,
        }),
    );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-text">{t("mcp.page.allTools")}</h3>
        {rows.length > 0 ? (
          <span className="text-xs text-text-muted" data-testid="mcp-tools-on">
            {t("mcp.page.toolsOn", { on, total: rows.length })}
          </span>
        ) : null}
        <span className="ml-auto inline-flex items-center gap-1">
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder={t("mcp.page.searchTools")}
            ariaLabel={t("mcp.page.searchTools")}
            className="w-48"
          />
          <Button
            variant="link"
            size="sm"
            disabled={bulk.isPending || rows.length === 0 || on === rows.length}
            onClick={() => setAll("enable")}
          >
            {t("mcp.page.allOn")}
          </Button>
          <span aria-hidden className="text-text-subtle">
            ·
          </span>
          <Button
            variant="link"
            size="sm"
            disabled={bulk.isPending || on === 0}
            onClick={() => setAll("disable")}
          >
            {t("mcp.page.allOff")}
          </Button>
        </span>
      </div>
      {pending ? (
        <Skeleton className="h-40 w-full" />
      ) : rows.length === 0 ? (
        <NoTools state={state} error={error} />
      ) : (
        <>
          {fromCache ? (
            <p className="text-xs text-text-muted">{cacheNote(t, state, detail)}</p>
          ) : null}
          {matching.length === 0 ? (
            <p className="py-2 text-xs text-text-muted">{t("mcp.capabilities.noMatches")}</p>
          ) : (
            <McpToolTable
              serverUid={serverUid}
              rows={matching.slice(0, TAB_SHOWN)}
              showListing={rows.some((r) => r.listing !== null)}
              fromCache={fromCache}
              label={t("mcp.server.tabs.tools")}
            />
          )}
          {matching.length > TAB_SHOWN ? (
            <p className="px-2 text-xs text-text-muted">
              {t("mcp.page.showingOf", { shown: TAB_SHOWN, total: matching.length })}
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
