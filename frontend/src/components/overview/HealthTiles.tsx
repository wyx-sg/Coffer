// src/components/overview/HealthTiles.tsx — the Overview's Health grid: one tile per sidebar area that is switched on.
//
// Each tile reads its own list hook for its number and the shared attention
// list for its status word, so it loads and fails on its own. An area whose
// feature is off (or not known yet) has no tile — hidden, not faked. An item
// ignored on Needs you is not in the list's `items`, so it does not count
// against its tile either: Coffer stopped asking about it.
import { useTranslation } from "react-i18next";

import { useAttention } from "@/lib/hooks/useAttention";
import { isFeatureOn, useFeatureMap } from "@/lib/hooks/useFeatures";
import { AREAS } from "@/lib/overview/health";
import { AreaHealthTile } from "./areaTiles";

export function HealthTiles() {
  const { t } = useTranslation();
  const attention = useAttention();
  const features = useFeatureMap();
  const shown = AREAS.filter((a) => isFeatureOn(features, a.feature));
  const items = attention.data?.items;
  return (
    <section aria-labelledby="overview-health" className="space-y-2">
      <h2 id="overview-health" className="flex min-h-[22px] items-center text-sm font-semibold">
        {t("overview.health.title")}
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {shown.map((area) => (
          <AreaHealthTile key={area.id} area={area} items={items} />
        ))}
      </div>
    </section>
  );
}
