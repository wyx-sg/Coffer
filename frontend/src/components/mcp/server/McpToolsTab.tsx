// src/components/mcp/server/McpToolsTab.tsx — the open server's Tools tab: Search tools, the table (design 4.1.10).
//
// Every tool in the server's own order, with its switch,
// rendered whole (100 at a time as the end scrolls into view, past 100) while the
// search runs over all of them. Ticking rows (or the header box, which ticks
// every tool the search matches) swaps the toolbar for the selection bar: Turn
// on, Turn off and, while tiering is on, an Exposure menu, all acting on the
// ticked tools only. A list rebuilt from the saved switches (the server could
// not be reached) says so: the switches still apply when it answers.
import { useState } from "react";
import { ListSelectionBar } from "@/components/ListSelectionBar";
import { useTableSelection } from "@/components/DataTableSelection";
import { BulkOnOffActions } from "@/components/BulkOnOffActions";
import { useTranslation } from "react-i18next";

import { BulkExposureMenu } from "./BulkExposureMenu";
import { CapabilityToolbar } from "./CapabilityToolbar";
import { LoadMoreSentinel } from "@/components/ui/load-more";
import { Skeleton } from "@/components/ui/skeleton";
import { mcpCapabilitiesKey, mcpTieringKey } from "@/lib/api/queryKeys";
import type { components } from "@/lib/api/types";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { useSetToolExposure } from "@/lib/hooks/useMcpToolExposure";
import { useGrowingList } from "@/lib/hooks/useGrowingList";
import type { ToolExposureMode } from "@/lib/api/mcpServers";
import { capabilitiesApi } from "@/lib/hooks/useMcpCapabilityMutations";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import type { InvocationSummary, ToolTiering } from "@/lib/hooks/useMcpServerPage";
import { McpToolTable } from "./McpToolTable";
import { NoTools } from "./McpTopTools";
import type { ServerState } from "@/lib/mcp/serverState";
import { cacheNote, countsUsage, toolRows, type ToolRow } from "./toolRows";

const rowKey = (row: ToolRow) => row.key;

type CapabilityListOut = components["schemas"]["CapabilityListOut"];

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
  const q = query.trim().toLowerCase();
  const matching = q ? rows.filter((r) => r.key.toLowerCase().includes(q)) : rows;
  const fromCache = capabilities?.from_cache ?? false;
  const page = useGrowingList(matching, q);
  const exposure = useSetToolExposure();
  const selection = useTableSelection(matching, rowKey);
  const selected = selection.selectedRows;
  const exposable = selected.filter((r) => r.enabled).map((r) => r.key);
  const exposeSelected = (mode: ToolExposureMode) =>
    exposure.mutate({ serverUid, tools: exposable, mode }, { onSuccess: selection.clear });

  const setSelected = async (op: "enable" | "disable") => {
    await bulk.run(
      selected.filter((r) => r.enabled !== (op === "enable")),
      (r) =>
        capabilitiesApi.setEnabled(op, {
          serverUid,
          capabilityType: "tool",
          capabilityKey: r.key,
        }),
    );
    selection.clear();
  };

  return (
    <div className="flex flex-col gap-3">
      {selected.length > 0 ? (
        <ListSelectionBar
          label={t("mcp.page.bulkTools")}
          count={selected.length}
          total={matching.length}
          onClear={selection.clear}
        >
          <BulkOnOffActions
            busy={bulk.isPending}
            offCount={selected.filter((r) => !r.enabled).length}
            onCount={selected.filter((r) => r.enabled).length}
            onTurnOn={() => void setSelected("enable")}
            onTurnOff={() => void setSelected("disable")}
          />
          {tiering?.enabled ? (
            <BulkExposureMenu
              disabled={exposure.isPending || exposable.length === 0}
              onPick={exposeSelected}
            />
          ) : null}
        </ListSelectionBar>
      ) : (
        <CapabilityToolbar
          placeholder={t("mcp.page.searchTools")}
          query={query}
          onQueryChange={setQuery}
        />
      )}
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
              rows={page.shown}
              showListing={rows.some((r) => r.exposure !== null || r.listing !== null)}
              fromCache={fromCache}
              label={t("mcp.server.tabs.tools")}
              selection={{
                keys: selection.keys,
                toggle: selection.toggle,
                allKeys: matching.map(rowKey),
                setMany: selection.setMany,
                count: selected.length,
              }}
            />
          )}
          <LoadMoreSentinel
            active={page.hasMore}
            onVisible={page.more}
            version={page.shown.length}
          />
        </>
      )}
    </div>
  );
}
