// src/components/usage/BreakdownTable.tsx — the range broken down by model, agent or day, with a Total row.
//
// By model names the provider that served each model beneath it and, in
// "Agent", who used it; by agent lists the agents; by day lists the local days
// newest first with each day's top agent, the latest week first and the rest
// behind "Show all".
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { agentTypeLabel } from "@/lib/agents/display";
import type { UsageSummary, UsageSummaryRow, UsageTotals } from "@/lib/api/usage";
import { formatDay, formatTokens } from "@/lib/usage/format";
import { localDay, parseDay } from "@/lib/usage/range";
import { CostCell, RequestsCell } from "./UsageCells";

interface Props {
  summary: UsageSummary;
  /** "Total · 7 days" — the range as the period control names it. */
  totalLabel: string;
}

const NUM = "text-right whitespace-nowrap";
/** Days shown before "Show all". */
const DAYS_SHOWN = 7;

export function BreakdownTable({ summary, totalLabel }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const [allDays, setAllDays] = useState(false);
  const tokens = (n: number) => (n ? formatTokens(n, lang) : "—");
  const by = summary.group_by;
  const byDay = by === "day";
  const hasSecond = by !== "agent";
  const today = localDay(new Date());
  const ordered = byDay ? [...summary.rows].reverse() : summary.rows;
  const hidden = byDay && !allDays ? Math.max(0, ordered.length - DAYS_SHOWN) : 0;
  const rows = hidden ? ordered.slice(0, DAYS_SHOWN) : ordered;

  const first = (row: UsageSummaryRow): ReactNode => {
    if (by === "agent") {
      return row.agent_type ? agentTypeLabel(row.agent_type) : t("usage.table.unknownAgent");
    }
    if (byDay) {
      if (!row.day) return row.key;
      const day = formatDay(parseDay(row.day), lang, "long");
      return row.day === today ? t("usage.table.today", { day }) : day;
    }
    return (
      <span className="flex min-w-0 flex-col gap-px">
        <span className="truncate font-mono text-xs font-medium">
          {row.model ?? t("usage.table.unknownModel")}
        </span>
        {row.connection_name ? (
          <span className="truncate text-2xs text-text-subtle">{row.connection_name}</span>
        ) : null}
      </span>
    );
  };

  const second = (row: UsageSummaryRow): ReactNode => {
    const names = byDay ? row.agent_types.slice(0, 1) : row.agent_types;
    return names.length ? names.map(agentTypeLabel).join(", ") : null;
  };

  const numbers = (totals: UsageTotals) => (
    <>
      <TableCell className={NUM}>
        <RequestsCell totals={totals} />
      </TableCell>
      <TableCell className={NUM}>{tokens(totals.input_tokens)}</TableCell>
      <TableCell className={NUM}>{tokens(totals.output_tokens)}</TableCell>
      <TableCell className={NUM}>{tokens(totals.cache_read_tokens)}</TableCell>
      <TableCell className={NUM}>
        {tokens(totals.cache_write_5m_tokens + totals.cache_write_1h_tokens)}
      </TableCell>
      <TableCell className={NUM}>
        <CostCell totals={totals} />
      </TableCell>
    </>
  );

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface-raised">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t(`usage.table.cols.${by}`)}</TableHead>
            {hasSecond ? <TableHead>{t(`usage.table.cols.second.${by}`)}</TableHead> : null}
            {(["requests", "input", "output", "cacheRead", "cacheWrite", "cost"] as const).map(
              (c) => (
                <TableHead key={c} className="text-right">
                  {t(`usage.table.cols.${c}`)}
                </TableHead>
              ),
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.key}>
              <TableCell className="max-w-0 w-full">{first(row)}</TableCell>
              {hasSecond ? (
                <TableCell className="whitespace-nowrap text-text-muted">{second(row)}</TableCell>
              ) : null}
              {numbers(row.totals)}
            </TableRow>
          ))}
          {hidden ? (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={8} className="text-xs text-text-muted">
                {t("usage.table.showing", { shown: rows.length, total: ordered.length })}
                {" · "}
                <button
                  type="button"
                  className="font-label text-accent-text hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
                  onClick={() => setAllDays(true)}
                >
                  {t("usage.table.showAll")}
                </button>
              </TableCell>
            </TableRow>
          ) : null}
        </TableBody>
        <TableFooter>
          <TableRow className="hover:bg-transparent">
            <TableCell colSpan={hasSecond ? 2 : 1}>
              {t("usage.table.total", { range: totalLabel })}
            </TableCell>
            {numbers(summary.totals)}
          </TableRow>
        </TableFooter>
      </Table>
    </div>
  );
}
