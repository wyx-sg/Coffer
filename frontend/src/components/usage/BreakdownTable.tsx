// src/components/usage/BreakdownTable.tsx — the range broken down by model, agent or day, with a Total row.
//
// By model names the connection that served each model (by name, as the
// summary reports it) and, in "By", the marks of the agents that used it; by
// agent names the agent and tags a subscription agent's rows "via API key";
// by day lists the local days newest first with each day's top agent, the
// latest week first and the rest behind "Show all".
import { useState, type ReactNode } from "react";
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
import { localDay, parseDay } from "@/lib/usage/range";
import { CostCell, RequestsCell } from "./UsageCells";
import { ViaApiKeyTag } from "./ViaApiKeyTag";

interface Props {
  summary: UsageSummary;
  /** "Total · 7 days" — the range as the period control names it. */
  totalLabel: string;
  /** Agent types on a subscription login: their rows carry "via API key". */
  subscriptionAgents: ReadonlySet<string>;
}

const NUM = "text-right whitespace-nowrap";
/** Days shown before "Show all". */
const DAYS_SHOWN = 7;

export function BreakdownTable({ summary, totalLabel, subscriptionAgents }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const [allDays, setAllDays] = useState(false);
  const tokens = (n: number) => (n ? formatTokens(n, lang) : "—");
  const byDay = summary.group_by === "day";
  const today = localDay(new Date());
  const ordered = byDay ? [...summary.rows].reverse() : summary.rows;
  const hidden = byDay && !allDays ? Math.max(0, ordered.length - DAYS_SHOWN) : 0;
  const rows = hidden ? ordered.slice(0, DAYS_SHOWN) : ordered;

  const first = (row: UsageSummaryRow): ReactNode => {
    if (summary.group_by === "agent") {
      if (!row.agent_type) return t("usage.table.unknownAgent");
      return <span className="text-sm">{agentTypeLabel(row.agent_type)}</span>;
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
          <span className="truncate text-2xs text-text-muted">{row.connection_name}</span>
        ) : null}
      </span>
    );
  };

  const second = (row: UsageSummaryRow): ReactNode => {
    if (summary.group_by === "agent") {
      return row.agent_type && subscriptionAgents.has(row.agent_type) ? <ViaApiKeyTag /> : null;
    }
    if (byDay) {
      const top = row.agent_types[0];
      return top ? (
        <span className="whitespace-nowrap text-sm text-text-muted">{agentTypeLabel(top)}</span>
      ) : null;
    }
    return (
      <span className="flex items-center gap-1">
        {row.agent_types.map((a) => (
          <AgentBadge key={a} type={a} size="sm" />
        ))}
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
          <TableHead>{t(`usage.table.cols.second.${summary.group_by}`)}</TableHead>
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
            <TableCell>{second(row)}</TableCell>
            {numbers(row.totals)}
          </TableRow>
        ))}
        {hidden ? (
          <TableRow className="hover:bg-transparent">
            <TableCell colSpan={8} className="text-xs text-text-muted">
              {t("usage.table.earlierDays", { count: hidden })}{" "}
              <button
                type="button"
                className="font-label text-accent-text hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
                onClick={() => setAllDays(true)}
              >
                {t("usage.table.showAllDays", { count: ordered.length })}
              </button>
            </TableCell>
          </TableRow>
        ) : null}
      </TableBody>
      <TableFooter>
        <TableRow className="hover:bg-transparent">
          <TableCell colSpan={2}>{t("usage.table.total", { range: totalLabel })}</TableCell>
          {numbers(summary.totals)}
        </TableRow>
      </TableFooter>
    </Table>
  );
}
