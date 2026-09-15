// frontend/src/components/memory/MemoryConflictsPanel.tsx
//
// Conflicts as pairs to settle (spec memory User Story 4 / FR-030/FR-033):
// two facts organise flagged as disagreeing, shown side by side, the
// developer picks one. Settling writes the `settle` override — a
// model's *proposal* is not a decision, so this is the only surface that can
// turn one into the other.
//
// A pair is derived from `conflicts_with` on the raw facts, not recomputed
// with overrides applied (the management endpoints intentionally show the raw
// facts — see `useMemory.ts`), so a pair already settled is filtered out here
// by checking the overrides table directly: once EITHER side carries a
// `conflict_choice`, the pair is resolved even though the stale
// `conflicts_with` on disk will not clear until the next organise pass
// (application/memory/overrides.py's `apply()` runs only at delivery/recall
// time, never rewriting the fact files themselves).
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { FactSummaryOut, OverrideOut } from "@/lib/api/memoryTypes";
import { useSetOverride } from "@/lib/hooks/useMemory";

interface ConflictPair {
  a: FactSummaryOut;
  b: FactSummaryOut;
}

function buildPairs(
  facts: FactSummaryOut[],
  overridesByKey: Map<string, OverrideOut>,
): ConflictPair[] {
  const byKey = new Map(facts.map((f) => [f.key, f]));
  const pairs: ConflictPair[] = [];
  const seen = new Set<string>();

  for (const fact of facts) {
    for (const otherKey of fact.conflicts_with) {
      const pairId = [fact.key, otherKey].sort().join("::");
      if (seen.has(pairId)) continue;
      seen.add(pairId);
      const other = byKey.get(otherKey);
      if (!other) continue; // the fact it once named may have aged out
      const settled =
        Boolean(overridesByKey.get(fact.key)?.conflict_choice) ||
        Boolean(overridesByKey.get(otherKey)?.conflict_choice);
      if (settled) continue;
      const [a, b] = fact.key < otherKey ? [fact, other] : [other, fact];
      pairs.push({ a, b });
    }
  }
  return pairs;
}

function ConflictSide({
  fact,
  onKeep,
  busy,
}: {
  fact: FactSummaryOut;
  onKeep: () => void;
  busy: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex-1 space-y-2 rounded-md border border-border/60 p-3">
      <div className="flex items-center gap-2">
        <span className="font-medium">{fact.title}</span>
        {fact.proposed ? <Badge variant="outline">{t("memory.status.proposedBadge")}</Badge> : null}
      </div>
      <p className="text-sm text-muted-foreground">{fact.description}</p>
      <Button type="button" size="sm" variant="outline" disabled={busy} onClick={onKeep}>
        {t("memory.conflicts.keepThis")}
      </Button>
    </div>
  );
}

export function MemoryConflictsPanel({
  facts,
  overrides,
}: {
  facts: FactSummaryOut[];
  overrides: OverrideOut[];
}) {
  const { t } = useTranslation();
  const setOverride = useSetOverride();
  const overridesByKey = new Map(overrides.map((o) => [o.fact_key, o]));
  const pairs = buildPairs(facts, overridesByKey);

  if (pairs.length === 0) return null;

  const settle = (pair: ConflictPair, chosen: FactSummaryOut) =>
    setOverride.mutate({ factKey: pair.a.key, patch: { conflict_choice: chosen.key } });

  return (
    <Card data-testid="memory-conflicts-panel">
      <CardHeader>
        <CardTitle className="text-base">{t("memory.conflicts.title")}</CardTitle>
        <p className="text-sm text-muted-foreground">{t("memory.conflicts.subtitle")}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        {pairs.map((pair) => (
          <div
            key={`${pair.a.key}::${pair.b.key}`}
            className="flex flex-col gap-2 sm:flex-row"
            data-testid={`memory-conflict-pair-${pair.a.slug}-${pair.b.slug}`}
          >
            <ConflictSide
              fact={pair.a}
              busy={setOverride.isPending}
              onKeep={() => settle(pair, pair.a)}
            />
            <ConflictSide
              fact={pair.b}
              busy={setOverride.isPending}
              onKeep={() => settle(pair, pair.b)}
            />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
