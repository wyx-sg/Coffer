// src/components/mcp/server/McpTopTools.tsx — the Overview's first few tools, busiest first, with "Show N more" to the Tools tab (design 4.1.02).
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Skeleton } from "@/components/ui/skeleton";
import type { components } from "@/lib/api/types";
import type { InvocationSummary, ToolTiering } from "@/lib/hooks/useMcpServerPage";
import { ToggleSwitch } from "../CapabilityRowCells";
import { toRows } from "../capabilityRows";
import { listingOf, usageByTool } from "./serverState";

type CapabilityListOut = components["schemas"]["CapabilityListOut"];

const SHOWN = 4;

interface Props {
  serverUid: string;
  capabilities: CapabilityListOut | undefined;
  pending: boolean;
  error: unknown;
  summary: InvocationSummary | undefined;
  tiering: ToolTiering | null | undefined;
  toolsHref: string;
}

export function McpTopTools({
  serverUid,
  capabilities,
  pending,
  error,
  summary,
  tiering,
  toolsHref,
}: Props) {
  const { t } = useTranslation();
  if (pending) return <Skeleton className="h-24 w-full" />;
  if (error) return <p className="text-xs text-text-muted">{t("mcp.capabilities.loadError")}</p>;
  const rows = toRows({ kind: "tool", tools: capabilities?.tools });
  if (rows.length === 0)
    return <p className="text-xs text-text-muted">{t("mcp.capabilities.emptyTool")}</p>;
  const usage = usageByTool(summary);
  const listing = listingOf(tiering);
  const busiest = [...rows].sort(
    (a, b) => (usage.get(b.key)?.calls ?? 0) - (usage.get(a.key)?.calls ?? 0),
  );
  const on = rows.filter((r) => r.enabled).length;

  return (
    <div className="flex flex-col gap-1">
      <p className="text-xs text-text-muted">{t("mcp.page.toolsOn", { on, total: rows.length })}</p>
      {capabilities?.from_cache ? (
        <p className="text-xs text-text-muted">{t("mcp.page.fromCache")}</p>
      ) : null}
      <ul className="flex flex-col" aria-label={t("mcp.server.tabs.tools")}>
        {busiest.slice(0, SHOWN).map((row) => (
          <li
            key={row.key}
            className="flex items-center gap-3 border-t border-border-subtle py-2 first:border-t-0"
          >
            <ToggleSwitch serverUid={serverUid} kind="tool" row={row} />
            <span className="flex min-w-0 flex-1 flex-col">
              <code className="truncate text-xs font-semibold">{row.key}</code>
              {row.description ? (
                <span className="truncate text-xs text-text-muted">{row.description}</span>
              ) : null}
            </span>
            {listing ? (
              <span className="text-xs text-text-muted">
                {listing.behind.has(row.key) ? t("mcp.page.behindSearch") : t("mcp.page.listed")}
              </span>
            ) : null}
            <span className="w-16 text-right text-xs tabular-nums text-text">
              {t("mcp.page.callsShort", { count: usage.get(row.key)?.calls ?? 0 })}
            </span>
          </li>
        ))}
      </ul>
      {rows.length > SHOWN ? (
        <Link to={toolsHref} className="text-xs text-accent hover:underline">
          {t("mcp.page.showMore", { count: rows.length - SHOWN })}
        </Link>
      ) : null}
    </div>
  );
}
