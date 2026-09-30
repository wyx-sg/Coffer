// src/components/mcp/server/McpToolsTab.tsx — the open server's tools: how many are on, All on · All off, and the table (design 4.1.02, 4.1.06).
//
// The table is the shared CapabilityList, given each tool's last-24-hours calls
// and errors and — while tiering hides any — whether agents see it listed or
// reach it through search. A list rebuilt from the saved switches (the server
// could not be reached) says so: the switches still apply when it answers.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { components } from "@/lib/api/types";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { capabilitiesApi } from "@/lib/hooks/useMcpCapabilityMutations";
import type { InvocationSummary, ToolTiering } from "@/lib/hooks/useMcpServerPage";
import { mcpCapabilitiesKey, mcpTieringKey } from "@/lib/api/queryKeys";
import { CapabilityList } from "../CapabilityList";
import { listingOf, usageByTool } from "./serverState";

type CapabilityListOut = components["schemas"]["CapabilityListOut"];

interface Props {
  serverUid: string;
  capabilities: CapabilityListOut | undefined;
  error: unknown;
  summary: InvocationSummary | undefined;
  tiering: ToolTiering | null | undefined;
}

export function McpToolsTab({ serverUid, capabilities, error, summary, tiering }: Props) {
  const { t } = useTranslation();
  const bulk = useBulkMutate({
    invalidate: [mcpCapabilitiesKey(serverUid), mcpTieringKey(serverUid)],
  });
  const tools = capabilities?.tools ?? [];
  const on = tools.filter((tool) => tool.enabled).length;

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
      {tools.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-text" data-testid="mcp-tools-on">
            {t("mcp.page.toolsOn", { on, total: tools.length })}
          </span>
          <Button
            variant="link"
            size="sm"
            disabled={bulk.isPending || on === tools.length}
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
        </div>
      ) : null}
      <CapabilityList
        serverUid={serverUid}
        kind="tool"
        tools={capabilities?.tools}
        error={error}
        fromCache={capabilities?.from_cache}
        usage={usageByTool(summary)}
        listing={listingOf(tiering)}
      />
    </div>
  );
}
