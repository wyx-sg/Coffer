// src/components/mcp/server/McpTopTools.tsx — the Overview's "Most-called tools": the busiest few, with "Show all N in Tools" (design 4.1.02–4.1.06).
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Skeleton } from "@/components/ui/skeleton";
import type { components } from "@/lib/api/types";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import type { InvocationSummary, ToolTiering } from "@/lib/hooks/useMcpServerPage";
import { McpToolTable } from "./McpToolTable";
import type { ServerState } from "@/lib/mcp/serverState";
import { busiestFirst, cacheNote, countsUsage, toolRows } from "./toolRows";

type CapabilityListOut = components["schemas"]["CapabilityListOut"];

const SHOWN = 4;

/** What the tools block says when there is no list to show. */
export function NoTools({ state, error }: { state: ServerState; error: unknown }) {
  const { t } = useTranslation();
  const text = error
    ? t("mcp.capabilities.loadError")
    : state.group === "attention"
      ? t("mcp.page.noToolsYet")
      : t("mcp.capabilities.emptyTool");
  return <p className="py-2 text-xs text-text-muted">{text}</p>;
}

interface Props {
  serverUid: string;
  state: ServerState;
  detail: McpStatusDetail | null | undefined;
  capabilities: CapabilityListOut | undefined;
  pending: boolean;
  error: unknown;
  summary: InvocationSummary | undefined;
  tiering: ToolTiering | null | undefined;
  toolsHref: string;
}

export function McpTopTools({
  serverUid,
  state,
  detail,
  capabilities,
  pending,
  error,
  summary,
  tiering,
  toolsHref,
}: Props) {
  const { t } = useTranslation();
  const rows = toolRows(capabilities?.tools, summary, tiering, countsUsage(state));
  const on = rows.filter((r) => r.enabled).length;
  const fromCache = capabilities?.from_cache ?? false;

  return (
    <section className="flex flex-col gap-2" aria-labelledby="mcp-top-tools">
      <div className="flex items-baseline gap-2">
        <h3 id="mcp-top-tools" className="text-sm font-semibold text-text">
          {t("mcp.page.mostCalled")}
        </h3>
        {rows.length > 0 ? (
          <span className="text-xs text-text-muted">
            {t("mcp.page.toolsOn", { on, total: rows.length })}
          </span>
        ) : null}
      </div>
      {pending ? (
        <Skeleton className="h-24 w-full" />
      ) : rows.length === 0 ? (
        <NoTools state={state} error={error} />
      ) : (
        <>
          {fromCache ? (
            <p className="text-xs text-text-muted">{cacheNote(t, state, detail)}</p>
          ) : null}
          <McpToolTable
            serverUid={serverUid}
            rows={busiestFirst(rows).slice(0, SHOWN)}
            showListing={rows.some((r) => r.listing !== null)}
            fromCache={fromCache}
            label={t("mcp.page.mostCalled")}
          />
          {rows.length > SHOWN ? (
            <Link to={toolsHref} className="px-2 pt-1 text-xs text-accent hover:underline">
              {t("mcp.page.showAllInTools", { count: rows.length })}
            </Link>
          ) : null}
        </>
      )}
    </section>
  );
}
