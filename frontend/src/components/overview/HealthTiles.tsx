// src/components/overview/HealthTiles.tsx — the Overview's Health grid: one tile per area that has a backend and is switched on.
//
// Each tile reads its own list hook for its number and the shared attention
// list for its status word, so it loads and fails on its own. An area whose
// feature is off (or not known yet) has no tile; custom tools and CLIs have
// no backend yet and so no tile at all — hidden, not faked.
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
  return (
    <section aria-labelledby="overview-health" className="space-y-3">
      <h2 id="overview-health" className="text-sm font-semibold">
        {t("overview.health.title")}
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {shown.map((area) => (
          <AreaHealthTile key={area.id} area={area} items={attention.data?.items} />
        ))}
      </div>
    </section>
  );
}
