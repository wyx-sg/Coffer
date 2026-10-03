// src/lib/overview/allGood.ts — the calm card's one sentence: what is fine, from what the Overview already reads.
//
// "Both agents are connected, 12 servers are answering and your vault is in
// sync. Anything that needs you shows up here." (Overview board 1.2.03). Each
// clause is there only when its area has something to report: no agent, no
// enabled server or a sync that is off, not set up or holding changes leaves
// its clause out, and with no clause the card says only where problems appear.
import type { TFunction } from "i18next";

/** @ui-only What the sentence is built from; a field left out has nothing to say. */
export interface AllGoodFacts {
  agents?: number;
  /** Enabled MCP servers. */
  servers?: number;
  /** Sync is on, set up, and has nothing held or in conflict. */
  vaultInSync?: boolean;
}

function agentsClause(t: TFunction, count: number): string {
  if (count === 1) return t("overview.needsYou.empty.agentsOne");
  if (count === 2) return t("overview.needsYou.empty.agentsBoth");
  return t("overview.needsYou.empty.agentsMany", { count });
}

/** The clauses that apply, in the order the sentence reads. */
function clauses(t: TFunction, facts: AllGoodFacts): string[] {
  const out: string[] = [];
  if (facts.agents) out.push(agentsClause(t, facts.agents));
  if (facts.servers) out.push(t("overview.needsYou.empty.servers", { count: facts.servers }));
  if (facts.vaultInSync) out.push(t("overview.needsYou.empty.vault"));
  return out;
}

/** "A, B and C." followed by where problems will show; just the latter with nothing to report. */
export function allGoodSummary(t: TFunction, facts: AllGoodFacts): string {
  const parts = clauses(t, facts);
  const tail = t("overview.needsYou.empty.body");
  if (parts.length === 0) return tail;
  const head =
    parts.length === 1
      ? parts[0]
      : parts.slice(0, -1).join(t("overview.needsYou.empty.sep")) +
        t("overview.needsYou.empty.and") +
        parts[parts.length - 1];
  return `${head.charAt(0).toUpperCase()}${head.slice(1)}${t("overview.needsYou.empty.stop")} ${tail}`;
}
