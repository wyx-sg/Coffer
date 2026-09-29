// src/lib/overview/health.ts — the Health tiles' areas, and the one status each derives from the attention list.
//
// A tile's number comes from its own list; whether it is healthy comes from
// the attention items of its kinds — one source per fact, so a tile can never
// say "All answering" beside a "Needs you" row about the same server.
import type { TFunction } from "i18next";

import type { FeatureKey } from "@/lib/hooks/useFeatures";
import type { AttentionItem } from "@/lib/hooks/useAttention";
import type { StatusTone } from "@/components/status/statusTone";

type AreaId =
  | "agents"
  | "providers"
  | "mcpServers"
  | "skills"
  | "channels"
  | "knowledge"
  | "memory"
  | "sync";

export interface Area {
  id: AreaId;
  /** The area's page — also the key its sidebar entry (label, icon) is found by. */
  to: string;
  /** The attention kinds whose items count against this area. */
  kinds: readonly string[];
  /** The experimental feature the area belongs to; the tile is hidden while it is off. */
  feature?: FeatureKey;
}

/** Every area with a backend, in sidebar order. Custom tools and CLIs have none yet, so no tile. */
export const AREAS: readonly Area[] = [
  { id: "agents", to: "/agents", kinds: ["agent"] },
  { id: "providers", to: "/model-providers", kinds: ["provider"] },
  { id: "channels", to: "/channels", kinds: ["channel"] },
  { id: "mcpServers", to: "/mcp-servers", kinds: ["mcp_server"] },
  { id: "skills", to: "/skills", kinds: ["skill"] },
  { id: "knowledge", to: "/knowledge", kinds: ["knowledge"], feature: "knowledge" },
  { id: "memory", to: "/memory", kinds: ["memory"], feature: "memory" },
  { id: "sync", to: "/sync", kinds: ["sync"], feature: "vault_sync" },
];

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

/** The uids the attention list reports about one kind — e.g. the agents that are not connected. */
export function uidsWithProblems(items: readonly AttentionItem[], kind: string): Set<string> {
  const out = new Set<string>();
  for (const item of items) if (item.kind === kind && item.uid) out.add(item.uid);
  return out;
}

/** How many distinct agents a set of skills is delivered to. */
export function deliveredAgentCount(
  skills: readonly { bindings: readonly { agent_uid: string }[] }[],
): number {
  return new Set(skills.flatMap((s) => s.bindings.map((b) => b.agent_uid))).size;
}

/** The tile's status word from the attention items of its kinds; none while unknown or empty. */
export function tileStatus(
  t: TFunction,
  area: Area,
  items: readonly AttentionItem[] | undefined,
  hasObjects: boolean,
): { tone: StatusTone; text: string } | null {
  if (!items || !hasObjects) return null;
  const status = areaStatus(areaProblems(items, area.kinds));
  if (status.tone === "err") {
    return { tone: "err", text: t("overview.health.failing", { count: status.count }) };
  }
  if (status.tone === "warn") {
    return { tone: "warn", text: t(`overview.health.${area.id}.warn`, { count: status.count }) };
  }
  return { tone: "ok", text: t(`overview.health.${area.id}.ok`) };
}
