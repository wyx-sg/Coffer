// src/components/usage/BreakdownTable.tsx — the range broken down by model, agent or day, with a Total row.
//
// By model names the connection that served each model (by name, as the
// summary reports it); by agent shows the agent's mark; by day the local day.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
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
import { parseDay } from "@/lib/usage/range";
import { CostCell, RequestsCell } from "./UsageCells";

interface Props {
  summary: UsageSummary;
  /** "Total · 7 days" — the range as the period control names it. */
  totalLabel: string;
}

const NUM = "text-right whitespace-nowrap";

export function BreakdownTable({ summary, totalLabel }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const tokens = (n: number) => (n ? formatTokens(n, lang) : "—");

  const first = (row: UsageSummaryRow): ReactNode => {
    if (summary.group_by === "agent") {
      if (!row.agent_type) return t("usage.table.unknownAgent");
      return (
        <span className="flex items-center gap-2">
          <AgentBadge type={row.agent_type} size="sm" tooltip={false} />
          <span className="text-sm font-label">{agentTypeLabel(row.agent_type)}</span>
        </span>
      );
    }
    if (summary.group_by === "day") {
      return row.day ? formatDay(parseDay(row.day), lang, "long") : row.key;
    }
    return (
      <span className="flex min-w-0 flex-col gap-px">
        <span className="truncate font-mono text-xs font-medium">
          {row.model ?? t("usage.table.unknownModel")}
        </span>
        {row.connection_name ? (
          <span className="truncate text-2xs text-text-muted">{row.connection_name}</span>
        ) : null}
      </span>
    );
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
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t(`usage.table.cols.${summary.group_by}`)}</TableHead>
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
        {summary.rows.map((row) => (
          <TableRow key={row.key}>
            <TableCell className="max-w-0 w-full">{first(row)}</TableCell>
            {numbers(row.totals)}
          </TableRow>
        ))}
      </TableBody>
      <TableFooter>
        <TableRow className="hover:bg-transparent">
          <TableCell>{t("usage.table.total", { range: totalLabel })}</TableCell>
          {numbers(summary.totals)}
        </TableRow>
      </TableFooter>
    </Table>
  );
}
