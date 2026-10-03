// src/components/usage/BreakdownTable.tsx — the range broken down by model, agent or day, in a bordered table with a Total row.
//
// By model names the connection that served each model (by name, as the
// summary reports it) and, in "By", the agents that used it; by agent lists
// the agents; by day lists the local days newest first with each day's top
// agent, the latest week first and the rest behind "Show all". The footer
// says what the cost leaves out and sends "Edit prices" to the Providers tab.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ShowAllRow } from "@/components/LongList";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useLongList } from "@/components/useLongList";
import { agentTypeLabel } from "@/lib/agents/display";
import type { UsageSummary, UsageSummaryRow, UsageTotals } from "@/lib/api/usage";
import { formatDay, formatTokens } from "@/lib/usage/format";
import { localDay, parseDay } from "@/lib/usage/range";
import { CostCell, RequestsCell } from "./UsageCells";

interface Props {
  summary: UsageSummary;
  /** "7 days" — the range as the Total row names it. */
  totalLabel: string;
  onEditPrices: () => void;
}

const NUM = "text-right whitespace-nowrap";
/** Days shown before "Show all". */
const DAYS_SHOWN = 7;

export function BreakdownTable({ summary, totalLabel, onEditPrices }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const tokens = (n: number) => (n ? formatTokens(n, lang) : "—");
  const group = summary.group_by;
  const today = localDay(new Date());
  const ordered = group === "day" ? [...summary.rows].reverse() : summary.rows;
  const { visible, shown, total, collapsed, expand, listClassName } = useLongList(ordered, {
    limit: DAYS_SHOWN,
    scrollInside: false,
  });
  const rows = group === "day" ? visible : ordered;
  const hasSecond = group !== "agent";
  const columns = (hasSecond ? 2 : 1) + 6;

  const first = (row: UsageSummaryRow): ReactNode => {
    if (group === "agent") {
      if (!row.agent_type) return t("usage.table.unknownAgent");
      return <span className="text-sm">{agentTypeLabel(row.agent_type)}</span>;
    }
    if (group === "day") {
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
          <span className="truncate text-xs text-text-subtle">{row.connection_name}</span>
        ) : null}
      </span>
    );
  };

  const second = (row: UsageSummaryRow): ReactNode => {
    const names = group === "day" ? row.agent_types.slice(0, 1) : row.agent_types;
    return names.length ? (
      <span className="whitespace-nowrap text-sm text-text-muted">
        {names.map(agentTypeLabel).join(", ")}
      </span>
    ) : null;
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
      <Table containerClassName={listClassName}>
        <TableHeader>
          <TableRow>
            <TableHead>{t(`usage.table.cols.${group}`)}</TableHead>
            {hasSecond ? <TableHead>{t(`usage.table.cols.second.${group}`)}</TableHead> : null}
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
              <TableCell className="w-full max-w-0">{first(row)}</TableCell>
              {hasSecond ? <TableCell>{second(row)}</TableCell> : null}
              {numbers(row.totals)}
            </TableRow>
          ))}
          {group === "day" && collapsed ? (
            <TableRow className="h-auto hover:bg-transparent">
              <TableCell colSpan={columns} className="p-0">
                <ShowAllRow shown={shown} total={total} onShowAll={expand} className="border-t-0" />
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
      <div className="flex items-center gap-1.5 border-t border-border-subtle bg-surface-footer px-3 py-2 text-xs text-text-muted">
        <span>{t("usage.table.footer")}</span>
        <Button variant="link" size="sm" className="h-auto p-0 text-xs" onClick={onEditPrices}>
          {t("usage.editPrices")}
        </Button>
      </div>
    </div>
  );
}
