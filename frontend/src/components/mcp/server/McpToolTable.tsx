// src/components/mcp/server/McpToolTable.tsx — the tool table the Overview and the Tools tab share (design 4.1.02, 4.1.06, 4.1.25).
//
// Header Tool · (Agents see it) · Calls 24 h · Errors; each row its switch,
// name and one-line description, whether it is listed or behind search, its
// calls and errors. A row opens to its full description, its input
// parameters, the name agents see, and its last call.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronRight, Search, TriangleAlert } from "lucide-react";

import { cn } from "@/lib/utils";
import { ToggleSwitch } from "../CapabilityRowCells";
import { CLIENT_NAME_LIMIT } from "../capabilityRows";
import { McpToolDetail } from "./McpToolDetail";
import type { ToolRow } from "./toolRows";

interface Props {
  serverUid: string;
  rows: readonly ToolRow[];
  /** Show the Listed / Behind search column (tiering hides some tools). */
  showListing: boolean;
  /** The list was rebuilt from saved switches: no descriptions or parameters. */
  fromCache: boolean;
  label: string;
}

const COLS = "w-28 text-right";
const NUM = "w-20 text-right tabular-nums";

function Count({ value, danger }: { value: number | null; danger?: boolean }) {
  if (value === null) return <span className="text-text-subtle">—</span>;
  return <span className={cn(danger && value > 0 ? "text-danger" : "text-text")}>{value}</span>;
}

export function McpToolTable({ serverUid, rows, showListing, fromCache, label }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState<string | null>(null);

  return (
    <div role="table" aria-label={label} className="flex flex-col text-sm">
      <div
        role="row"
        className="flex items-center gap-3 border-b border-border-subtle py-1.5 text-2xs font-semibold text-text-muted"
      >
        <span className="w-9" aria-hidden />
        <span role="columnheader" className="min-w-0 flex-1">
          {t("mcp.page.colTool")}
        </span>
        {showListing ? <span className={COLS} aria-hidden /> : null}
        <span role="columnheader" className={NUM}>
          {t("mcp.page.colCalls24h")}
        </span>
        <span role="columnheader" className={cn(NUM, "w-16 pr-2")}>
          {t("mcp.page.colErrors")}
        </span>
      </div>
      {rows.map((row) => {
        const expanded = open === row.key;
        return (
          <div key={row.key} role="rowgroup" className="border-b border-border-subtle">
            <div
              role="row"
              aria-expanded={expanded}
              tabIndex={0}
              className="group flex cursor-pointer items-center gap-3 py-2 hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring"
              onClick={() => setOpen(expanded ? null : row.key)}
              onKeyDown={(e) => {
                // The switch inside handles its own keys.
                if (e.target !== e.currentTarget) return;
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setOpen(expanded ? null : row.key);
                }
              }}
            >
              <span className="flex w-9 justify-center" role="cell">
                <ToggleSwitch serverUid={serverUid} kind="tool" row={row} />
              </span>
              <span role="cell" className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="flex items-center gap-1">
                  <code className="truncate text-xs font-semibold">{row.key}</code>
                  <ChevronRight
                    aria-hidden
                    className={cn(
                      "size-3 shrink-0 text-text-subtle opacity-0 transition-transform group-hover:opacity-100",
                      expanded && "rotate-90 opacity-100",
                    )}
                  />
                </span>
                {row.description ? (
                  <span className="truncate text-xs text-text-muted">{row.description}</span>
                ) : null}
                {row.tooLong ? (
                  <span className="flex items-start gap-1 text-xs text-warning" role="note">
                    <TriangleAlert className="mt-0.5 size-3 shrink-0" aria-hidden />
                    {t("mcp.page.nameTooLong", {
                      length: row.clientNameLength,
                      limit: CLIENT_NAME_LIMIT,
                    })}
                  </span>
                ) : null}
              </span>
              {showListing ? (
                <span role="cell" className={cn(COLS, "text-xs text-text-muted")}>
                  {row.listing === "behind" ? (
                    <span className="inline-flex items-center gap-1">
                      <Search className="size-3" aria-hidden /> {t("mcp.page.behindSearch")}
                    </span>
                  ) : row.listing === "listed" ? (
                    t("mcp.page.listed")
                  ) : null}
                </span>
              ) : null}
              <span role="cell" className={NUM}>
                <Count value={row.calls} />
              </span>
              <span role="cell" className={cn(NUM, "w-16 pr-2")}>
                <Count value={row.errors} danger />
              </span>
            </div>
            {expanded ? <McpToolDetail row={row} fromCache={fromCache} /> : null}
          </div>
        );
      })}
    </div>
  );
}
