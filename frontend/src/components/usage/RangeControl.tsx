// src/components/usage/RangeControl.tsx — the period control: Today · 7 days · 30 days · This month · Custom….
import { useTranslation } from "react-i18next";

import type { UsageQuery } from "@/lib/api/usage";
import { PRESET_RANGES } from "@/lib/usage/range";
import { CustomRangePopover } from "./CustomRangePopover";
import { segmentClass } from "./segment";

interface Props {
  query: UsageQuery;
  detailDays: number | null;
  onChange: (next: UsageQuery) => void;
}

export function RangeControl({ query, detailDays, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <div
      role="group"
      aria-label={t("usage.providers.period")}
      className="inline-flex flex-wrap gap-0.5 rounded-md border border-border-subtle bg-surface-sunken p-[3px]"
    >
      {PRESET_RANGES.map((r) => (
        <button
          key={r}
          type="button"
          aria-pressed={query.range === r}
          className={segmentClass(query.range === r)}
          onClick={() => onChange({ ...query, range: r, from: undefined, to: undefined })}
        >
          {t(`usage.providers.range.${r}`)}
        </button>
      ))}
      <CustomRangePopover
        from={query.from}
        to={query.to}
        active={query.range === "custom"}
        detailDays={detailDays}
        onApply={(from, to) => onChange({ ...query, range: "custom", from, to })}
      />
    </div>
  );
}
