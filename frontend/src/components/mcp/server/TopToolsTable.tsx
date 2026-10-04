// src/components/mcp/server/TopToolsTable.tsx — the Overview's read-only tool table: Tool · [Listed / Behind search] · Calls 24 h · Errors (design 4.1.04, 4.1.08).
import { useTranslation } from "react-i18next";
import { Search, TriangleAlert } from "lucide-react";

import { TruncatedText } from "@/components/ui/truncated-text";
import { cn } from "@/lib/utils";
import { CLIENT_NAME_LIMIT } from "../capabilityRows";
import type { ToolRow } from "./toolRows";

interface Props {
  rows: readonly ToolRow[];
  /** Tiering hides some tools: add the Listed / Behind search column. */
  showListing: boolean;
  label: string;
}

function Count({ value, danger }: { value: number | null; danger?: boolean }) {
  if (value === null) return <span className="text-text-subtle">—</span>;
  return <span className={cn(danger && value > 0 ? "text-danger" : "text-text")}>{value}</span>;
}

export function TopToolsTable({ rows, showListing, label }: Props) {
  const { t } = useTranslation();
  const grid = cn(
    "grid items-center gap-2.5",
    showListing
      ? "grid-cols-[minmax(0,1fr)_112px_80px_60px]"
      : "grid-cols-[minmax(0,1fr)_80px_60px]",
  );
  return (
    <div role="table" aria-label={label} className="flex flex-col">
      <div role="row" className={cn(grid, "pb-1.5 text-2xs font-semibold text-text-subtle")}>
        <span role="columnheader">{t("mcp.page.colTool")}</span>
        {showListing ? <span role="columnheader">{t("mcp.exposure.col")}</span> : null}
        <span role="columnheader" className="text-right">
          {t("mcp.page.colCalls24h")}
        </span>
        <span role="columnheader" className="text-right">
          {t("mcp.page.colErrors")}
        </span>
      </div>
      {rows.map((row) => (
        <div
          key={row.key}
          role="row"
          className={cn(grid, "border-t border-border-subtle py-[7px] text-xs tabular-nums")}
        >
          <span role="cell" className="flex min-w-0 flex-col gap-px">
            <TruncatedText text={row.key} mono className="text-xs font-medium" />
            {row.description ? (
              <TruncatedText text={row.description} className="text-xs text-text-muted" />
            ) : null}
            {row.tooLong ? (
              <span className="flex items-start gap-1 pt-0.5 text-xs text-warning" role="note">
                <TriangleAlert className="mt-0.5 size-3 shrink-0" aria-hidden />
                {t("mcp.page.nameTooLong", {
                  length: row.clientNameLength,
                  limit: CLIENT_NAME_LIMIT,
                })}
              </span>
            ) : null}
          </span>
          {showListing ? (
            <span role="cell" className="text-text-muted">
              {row.listing === "behind" ? (
                <span className="inline-flex items-center gap-1">
                  <Search className="size-3" aria-hidden /> {t("mcp.page.behindSearch")}
                </span>
              ) : row.listing === "listed" ? (
                t("mcp.page.listed")
              ) : null}
            </span>
          ) : null}
          <span role="cell" className="text-right">
            <Count value={row.calls} />
          </span>
          <span role="cell" className="text-right">
            <Count value={row.errors} danger />
          </span>
        </div>
      ))}
    </div>
  );
}
