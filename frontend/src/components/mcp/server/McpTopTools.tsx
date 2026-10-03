// src/components/mcp/server/McpTopTools.tsx — the Overview's "Most-called tools": the busiest few by 24-hour calls, read-only, with "Show all N in Tools" (design 4.1.04–4.1.08).
//
// No switches here (they live on the Tools tab). While tiering hides some
// tools the table adds a Listed / Behind search column.
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Section } from "@/components/Section";
import { Skeleton } from "@/components/ui/skeleton";
import type { components } from "@/lib/api/types";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import type { InvocationSummary, ToolTiering } from "@/lib/hooks/useMcpServerPage";
import { TopToolsTable } from "./TopToolsTable";
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
  name: string;
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
  name,
  state,
  detail,
  capabilities,
  pending,
  error,
  summary,
  tiering,
  toolsHref,
}: Props) {
  const location = useLocation();
  const { t } = useTranslation();
  const rows = toolRows(capabilities?.tools, summary, tiering, countsUsage(state));
  const fromCache = capabilities?.from_cache ?? false;

  return (
    <Section title={t("mcp.page.mostCalled")} gap="snug" labelled compact>
      <p className="-mt-1 text-xs text-text-muted">
        {fromCache && rows.length > 0
          ? cacheNote(t, state, detail)
          : t("mcp.page.mostCalledSub", { name })}
      </p>
      {pending ? (
        <Skeleton className="h-24 w-full" />
      ) : rows.length === 0 ? (
        <NoTools state={state} error={error} />
      ) : (
        <>
          <TopToolsTable
            rows={busiestFirst(rows).slice(0, SHOWN)}
            showListing={rows.some((r) => r.listing !== null)}
            label={t("mcp.page.mostCalled")}
          />
          {rows.length > SHOWN ? (
            <Link
              to={toolsHref}
              state={location.state}
              className="pt-1 text-xs font-label text-accent-text hover:underline"
            >
              {t("mcp.page.showAllInTools", { count: rows.length })}
            </Link>
          ) : null}
        </>
      )}
    </Section>
  );
}
