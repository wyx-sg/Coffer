// src/components/mcp/server/McpToolsTab.tsx — the open server's Tools tab: Search tools, N of M on, All on · All off, the table (design 4.1.10).
//
// Every tool in the server's own order, with its switch,
// rendered 50 at a time ("Showing N of M", Show more) while the search runs over
// all of them. The toolbar's menu sets the exposure of the filtered tools. A list rebuilt
// from the saved switches (the server could not be reached) says so: the
// switches still apply when it answers.
import { useState } from "react";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { useTranslation } from "react-i18next";

import { CapabilityToolbar } from "./CapabilityToolbar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { mcpCapabilitiesKey, mcpTieringKey } from "@/lib/api/queryKeys";
import type { components } from "@/lib/api/types";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { useSetToolExposure } from "@/lib/hooks/useMcpToolExposure";
import { useShowMore } from "@/lib/hooks/useShowMore";
import type { ToolExposureMode } from "@/lib/api/mcpServers";
import { capabilitiesApi } from "@/lib/hooks/useMcpCapabilityMutations";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import type { InvocationSummary, ToolTiering } from "@/lib/hooks/useMcpServerPage";
import { McpToolTable } from "./McpToolTable";
import { NoTools } from "./McpTopTools";
import type { ServerState } from "@/lib/mcp/serverState";
import { cacheNote, countsUsage, toolRows } from "./toolRows";

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
  const on = rows.filter((r) => r.enabled).length;
  const q = query.trim().toLowerCase();
  const matching = q ? rows.filter((r) => r.key.toLowerCase().includes(q)) : rows;
  const fromCache = capabilities?.from_cache ?? false;
  const page = useShowMore(matching, q);
  const exposure = useSetToolExposure();
  const exposureActions: MenuAction[] = (
    [
      ["auto", "bulkAuto"],
      ["listed", "bulkListed"],
      ["search", "bulkSearch"],
    ] as const
  ).map(([mode, key]: readonly [ToolExposureMode, string]) => ({
    key: mode,
    label: t(`mcp.exposure.${key}`, { count: matching.length }),
    disabled: exposure.isPending || matching.length === 0,
    onSelect: () => exposure.mutate({ serverUid, tools: matching.map((r) => r.key), mode }),
  }));

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
      <CapabilityToolbar
        placeholder={t("mcp.page.searchTools")}
        query={query}
        onQueryChange={setQuery}
        on={on}
        total={rows.length}
        busy={bulk.isPending}
        onAllOn={() => setAll("enable")}
        onAllOff={() => setAll("disable")}
        extra={
          tiering?.enabled ? (
            <ActionMenu label={t("mcp.exposure.bulk")} actions={exposureActions} />
          ) : null
        }
      />
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
            />
          )}
          {matching.length > 0 ? (
            <p className="flex items-center gap-2 px-2 text-xs text-text-muted">
              <span data-testid="mcp-tools-shown">
                {t("mcp.page.showingOf", { shown: page.shown.length, total: page.total })}
              </span>
              {page.hasMore ? (
                <Button variant="link" size="sm" onClick={page.showMore}>
                  {t("mcp.page.showMore", { count: page.next })}
                </Button>
              ) : null}
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
