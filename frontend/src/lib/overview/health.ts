// src/lib/overview/health.ts — the Health tiles' areas, and the one status each derives from the attention list.
//
// A tile's number comes from its own list; whether it is healthy comes from
// the attention items of its kinds — one source per fact, so a tile can never
// say "All answering" beside a "Needs you" row about the same server.
import type { TFunction } from "i18next";

import type { FeatureKey } from "@/lib/features";
import type { AttentionItem } from "@/lib/hooks/useAttention";
import type { StatusTone } from "@/lib/statusTone";

type AreaId =
  | "agents"
  | "providers"
  | "mcpServers"
  | "skills"
  | "channels"
  | "knowledge"
  | "memory"
  | "sync"
  | "customTools"
  | "clis"
  | "secrets"
  | "usage";

export interface Area {
  id: AreaId;
  /** The area's page — also the key its sidebar entry (label, icon) is found by. */
  to: string;
  /** The attention kinds whose items count against this area. */
  kinds: readonly string[];
  /** The experimental feature the area belongs to; the tile is hidden while it is off. */
  feature?: FeatureKey;
}

/** Every sidebar area but Overview, Conversations (they show in Recent
 *  activity) and Activity, in the board's order (Overview 1.3.01): what agents
 *  use first, then the system areas. */
export const AREAS: readonly Area[] = [
  { id: "agents", to: "/agents", kinds: ["agent"] },
  { id: "mcpServers", to: "/mcp-servers", kinds: ["mcp_server"] },
  { id: "skills", to: "/skills", kinds: ["skill"] },
  { id: "knowledge", to: "/knowledge", kinds: ["knowledge"], feature: "knowledge" },
  { id: "memory", to: "/memory", kinds: ["memory"], feature: "memory" },
  { id: "providers", to: "/model-providers", kinds: ["provider"], feature: "models" },
  { id: "channels", to: "/channels", kinds: ["channel"] },
  { id: "sync", to: "/sync", kinds: ["sync"], feature: "sync" },
  { id: "customTools", to: "/custom-tools", kinds: ["custom_tool"] },
  { id: "clis", to: "/clis", kinds: ["cli"] },
  { id: "secrets", to: "/secrets", kinds: [] },
  { id: "usage", to: "/usage", kinds: [], feature: "models" },
];

/** Agent items that are only about connecting — the rest (a hook changed by
 *  hand, a missing program) are problems of another sort, and the Agents tile
 *  neither counts them as "not connected" nor words them (Overview board
 *  1.2.05: "1 to connect" beside a hook edited by hand). */
export const CONNECT_REASONS: ReadonlySet<string> = new Set([
  "agent_not_connected",
  "agent_partial",
]);

/** The warning word a CLI tile uses when every item has the same reason; mixed
 *  reasons read the generic "need attention". */
const CLI_REASON_WORDS: Record<string, string> = {
  cli_logged_out: "notLoggedIn",
  cli_outdated: "outdated",
  cli_missing: "missing",
};

/** @ui-only An area's problems as the attention list reports them. */
export interface AreaProblems {
  errors: number;
  /** Warnings and informational items together — both read amber. */
  warnings: number;
}

/** How many of `items` are about `kinds`, by severity. */
export function areaProblems(
  items: readonly AttentionItem[],
  kinds: readonly string[],
): AreaProblems {
  let errors = 0;
  let warnings = 0;
  for (const item of items) {
    if (!kinds.includes(item.kind)) continue;
    if (item.severity === "error") errors += 1;
    else warnings += 1;
  }
  return { errors, warnings };
}

/** @ui-only The status word a tile shows: which tone, and how many it counts. */
export interface AreaStatus {
  tone: StatusTone;
  count: number;
}

/** Errors outrank warnings; nothing reported is ok. */
export function areaStatus(problems: AreaProblems): AreaStatus {
  if (problems.errors > 0) return { tone: "err", count: problems.errors };
  if (problems.warnings > 0) return { tone: "warn", count: problems.warnings };
  return { tone: "ok", count: 0 };
}

/** The uids the attention list reports about one kind — e.g. the agents that are not connected —
 *  optionally only for the given reasons. */
export function uidsWithProblems(
  items: readonly AttentionItem[],
  kind: string,
  reasons?: ReadonlySet<string>,
): Set<string> {
  const out = new Set<string>();
  for (const item of items) {
    if (item.kind === kind && item.uid && (!reasons || reasons.has(item.reason_code))) {
      out.add(item.uid);
    }
  }
  return out;
}

/** How many distinct agents a set of skills is delivered to. */
export function deliveredAgentCount(
  skills: readonly { bindings: readonly { agent_uid: string }[] }[],
): number {
  return new Set(skills.flatMap((s) => s.bindings.map((b) => b.agent_uid))).size;
}

/** The i18n key of an area's warning word: its own, a reason-specific one for CLIs, or the generic. */
function warnKey(area: Area, items: readonly AttentionItem[]): string {
  if (area.id !== "clis") return `overview.health.${area.id}.warn`;
  const codes = new Set(items.filter((i) => area.kinds.includes(i.kind)).map((i) => i.reason_code));
  const [only] = codes;
  const word = codes.size === 1 && only ? CLI_REASON_WORDS[only] : undefined;
  return word ? `overview.health.clis.${word}` : "overview.health.attention";
}

/** The tile's status word from the attention items of its kinds; none while unknown or empty. */
export function tileStatus(
  t: TFunction,
  area: Area,
  items: readonly AttentionItem[] | undefined,
  hasObjects: boolean,
): { tone: StatusTone; text: string } | null {
  if (!items || !hasObjects) return null;
  const scoped =
    area.id === "agents"
      ? items.filter((i) => i.kind !== "agent" || CONNECT_REASONS.has(i.reason_code))
      : items;
  const status = areaStatus(areaProblems(scoped, area.kinds));
  if (status.tone === "err") {
    return { tone: "err", text: t("overview.health.failing", { count: status.count }) };
  }
  if (status.tone === "warn") {
    return { tone: "warn", text: t(warnKey(area, scoped), { count: status.count }) };
  }
  return { tone: "ok", text: t(`overview.health.${area.id}.ok`) };
}
