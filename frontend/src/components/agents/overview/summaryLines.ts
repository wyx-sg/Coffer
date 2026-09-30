// src/components/agents/overview/summaryLines.ts — the one line under each "What this agent can use" row.
//
// Pure: counts in, sentence out. A count that has not loaded is `undefined`
// and yields `undefined` (the row shows a skeleton), never a zero.
import type { TFunction } from "i18next";

import type { AgentCounts } from "@/lib/agents/counts";

const K = "agents.overviewTab.summary";

export interface SummaryLine {
  line: string;
  /** How many of the agent's own entries wait for a look, when there are any. */
  toReview?: number;
}

interface Context {
  disabled: boolean;
  /** The file direct MCP entries sit in (`.claude.json`, `config.toml`). */
  mcpFile: string;
  /** Where Coffer links skills (`~/.codex/skills`). */
  skillDir: string;
  /** The one file every hook sits in, when they share one. */
  hookFile?: string;
}

function owned(own: number, disabled: boolean): number | undefined {
  return !disabled && own > 0 ? own : undefined;
}

export function mcpLine(
  t: TFunction,
  c: AgentCounts["mcp"],
  ctx: Context,
): SummaryLine | undefined {
  if (!c) return undefined;
  if (ctx.disabled) return { line: t(`${K}.disabledLine`, { count: c.coffer }) };
  const line =
    c.own > 0
      ? t(`${K}.mcp.line`, { coffer: c.coffer, own: c.own, file: ctx.mcpFile })
      : t(`${K}.mcp.lineCofferOnly`, { coffer: c.coffer });
  return { line, toReview: owned(c.own, ctx.disabled) };
}

export function skillsLine(
  t: TFunction,
  c: AgentCounts["skills"],
  ctx: Context,
): SummaryLine | undefined {
  if (!c) return undefined;
  if (ctx.disabled) return { line: t(`${K}.disabledLine`, { count: c.coffer }) };
  const line =
    c.own > 0
      ? t(`${K}.skills.line`, { coffer: c.coffer, own: c.own })
      : t(`${K}.skills.lineCofferOnly`, { coffer: c.coffer, dir: ctx.skillDir });
  return { line, toReview: owned(c.own, ctx.disabled) };
}

export function pluginsLine(t: TFunction, c: AgentCounts["plugins"]): SummaryLine | undefined {
  if (!c) return undefined;
  if (c.total === 0) return { line: t(`${K}.plugins.none`) };
  return {
    line: t(`${K}.plugins.line`, { count: c.marketplaces, total: c.total, enabled: c.enabled }),
  };
}

export function hooksLine(
  t: TFunction,
  c: AgentCounts["hooks"],
  ctx: Context,
): SummaryLine | undefined {
  if (!c) return undefined;
  if (c.total === 0) return { line: t(`${K}.hooks.none`) };
  const where = ctx.hookFile
    ? t(`${K}.hooks.inFile`, { count: c.total, file: ctx.hookFile })
    : t(`${K}.hooks.inPlaces`, { count: c.total, places: c.files });
  const line = c.coffer > 0 ? `${where} · ${t(`${K}.hooks.coffer`, { count: c.coffer })}` : where;
  return { line };
}

export function memoryLine(t: TFunction, stores: number | undefined): SummaryLine | undefined {
  if (stores === undefined) return undefined;
  return { line: stores === 0 ? t(`${K}.memory.none`) : t(`${K}.memory.line`, { count: stores }) };
}

export function configLine(t: TFunction, names: string[] | undefined): SummaryLine | undefined {
  if (names === undefined) return undefined;
  return { line: names.length === 0 ? t(`${K}.config.none`) : names.join(", ") };
}
