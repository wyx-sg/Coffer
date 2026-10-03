// src/components/agents/overview/summaryLines.ts — the one line under each "What this agent can use" row.
//
// Pure: counts in, sentence out. A count that has not loaded is `undefined`
// and yields `undefined` (the row shows a skeleton), never a zero.
import type { TFunction } from "i18next";

import type { AgentCounts } from "@/lib/agents/counts";

const K = "agents.overviewTab.summary";

export interface SummaryLine {
  /** The tile's big number. */
  count: number;
  line: string;
  /** How many of the agent's own entries wait for a look, when there are any. */
  toReview?: number;
}

interface Context {
  disabled: boolean;
  /** The agent has no `coffer` entry yet, so nothing reaches it through the gateway. */
  notConnected?: boolean;
  /** The file direct MCP entries sit in (`.claude.json`, `config.toml`). */
  mcpFile: string;
  /** Where Coffer links skills (`~/.codex/skills`). */
  skillDir: string;
  /** The one file every hook sits in, when they share one. */
  hookFile?: string;
}

/** How many direct entries wait for a look: duplicates of a server Coffer has. */
function duplicated(c: NonNullable<AgentCounts["mcp"]>, disabled: boolean): number | undefined {
  return !disabled && c.duplicates > 0 ? c.duplicates : undefined;
}

export function mcpLine(
  t: TFunction,
  c: AgentCounts["mcp"],
  ctx: Context,
): SummaryLine | undefined {
  if (!c) return undefined;
  if (ctx.disabled)
    return { count: c.coffer + c.own, line: t(`${K}.disabledLine`, { count: c.coffer }) };
  if (ctx.notConnected) {
    const until = t(`${K}.mcp.untilConnected`, { count: c.coffer });
    const line =
      c.own > 0 ? `${until} · ${t(`${K}.mcp.direct`, { own: c.own, file: ctx.mcpFile })}` : until;
    return { count: c.own, line, toReview: duplicated(c, ctx.disabled) };
  }
  const line =
    c.own > 0
      ? t(`${K}.mcp.line`, { coffer: c.coffer, own: c.own, file: ctx.mcpFile })
      : t(`${K}.mcp.lineCofferOnly`, { coffer: c.coffer });
  return { count: c.coffer + c.own, line, toReview: duplicated(c, ctx.disabled) };
}

export function skillsLine(
  t: TFunction,
  c: AgentCounts["skills"],
  ctx: Context,
): SummaryLine | undefined {
  if (!c) return undefined;
  if (ctx.disabled)
    return { count: c.coffer + c.own, line: t(`${K}.disabledLine`, { count: c.coffer }) };
  const line =
    c.own > 0
      ? t(`${K}.skills.line`, { coffer: c.coffer, own: c.own })
      : t(`${K}.skills.lineCofferOnly`, { coffer: c.coffer, dir: ctx.skillDir });
  return { count: c.coffer + c.own, line };
}

export function pluginsLine(t: TFunction, c: AgentCounts["plugins"]): SummaryLine | undefined {
  if (!c) return undefined;
  if (c.total === 0) return { count: 0, line: t(`${K}.plugins.none`) };
  return {
    count: c.total,
    line: t(`${K}.plugins.line`, { count: c.marketplaces, total: c.total, enabled: c.enabled }),
  };
}

export function hooksLine(
  t: TFunction,
  c: AgentCounts["hooks"],
  ctx: Context,
): SummaryLine | undefined {
  if (!c) return undefined;
  const cofferNote =
    c.cofferState === "missing"
      ? t(`${K}.hooks.cofferMissing`)
      : c.cofferState === "untrusted"
        ? t(`${K}.hooks.cofferUntrusted`)
        : c.coffer > 0
          ? t(`${K}.hooks.coffer`, { count: c.coffer })
          : null;
  if (c.total === 0) {
    return {
      count: 0,
      line: cofferNote ? `${t(`${K}.hooks.none`)} · ${cofferNote}` : t(`${K}.hooks.none`),
      toReview: c.cofferState ? 1 : undefined,
    };
  }
  const where = ctx.hookFile
    ? t(`${K}.hooks.inFile`, { count: c.total, file: ctx.hookFile })
    : t(`${K}.hooks.inPlaces`, { count: c.total, places: c.files });
  return {
    count: c.total,
    line: cofferNote ? `${where} · ${cofferNote}` : where,
    toReview: c.cofferState ? 1 : undefined,
  };
}

export function memoryLine(t: TFunction, stores: number | undefined): SummaryLine | undefined {
  if (stores === undefined) return undefined;
  return {
    count: stores,
    line: t(`${K}.memory.${stores === 0 ? "none" : "line"}`, { count: stores }),
  };
}

export function configLine(t: TFunction, names: string[] | undefined): SummaryLine | undefined {
  if (names === undefined) return undefined;
  return {
    count: names.length,
    line: names.length === 0 ? t(`${K}.config.none`) : names.join(", "),
  };
}
