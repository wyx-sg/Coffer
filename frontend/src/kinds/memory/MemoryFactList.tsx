// frontend/src/kinds/memory/MemoryFactList.tsx
//
// Every fact in one partition (spec memory FR-062), filterable by title —
// the corpus stays in the hundreds per partition (spec memory §Assumptions),
// so a client-side filter is enough; there is no server-side search route for
// facts. Hidden facts stay in this list (FR-042: absent from delivery, still
// visible and reversible here).
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import type { FactSummaryOut, OverrideOut } from "@/kinds/memory/types";
import { MemoryFactCard } from "@/kinds/memory/MemoryFactCard";

export function MemoryFactList({
  partition,
  facts,
  overrides,
}: {
  partition: string;
  facts: FactSummaryOut[];
  overrides: OverrideOut[];
}) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("");
  const overridesByKey = useMemo(() => new Map(overrides.map((o) => [o.fact_key, o])), [overrides]);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return facts;
    return facts.filter(
      (f) => f.title.toLowerCase().includes(q) || f.description.toLowerCase().includes(q),
    );
  }, [facts, filter]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-medium">{t("memory.detail.factsTitle")}</h2>
        <Input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t("memory.detail.filterPlaceholder")}
          aria-label={t("memory.detail.filterPlaceholder")}
          className="max-w-xs"
        />
      </div>

      {visible.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {facts.length === 0 ? t("memory.detail.factsEmpty") : t("memory.detail.noMatches")}
        </p>
      ) : (
        <div className="space-y-3">
          {visible.map((fact) => (
            <MemoryFactCard
              key={fact.key}
              fact={fact}
              partition={partition}
              override={overridesByKey.get(fact.key)}
              candidates={facts.filter((f) => f.key !== fact.key && f.status === "active")}
            />
          ))}
        </div>
      )}
    </div>
  );
}
