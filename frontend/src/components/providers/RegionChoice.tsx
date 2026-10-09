// src/components/providers/RegionChoice.tsx — International or Mainland China, for a vendor whose addresses (and keys) differ by region.
import { useTranslation } from "react-i18next";

import type { Region } from "@/lib/providers/addresses";
import { cn } from "@/lib/utils";

interface Props {
  value: Region;
  onChange: (region: Region) => void;
}

export function RegionChoice({ value, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-label text-text">{t("providers.region.label")}</span>
      <div role="radiogroup" aria-label={t("providers.region.label")} className="flex gap-1.5">
        {(["intl", "cn"] as const).map((r) => (
          <button
            key={r}
            type="button"
            role="radio"
            aria-checked={r === value}
            onClick={() => onChange(r)}
            className={cn(
              "h-7 rounded-md border px-3 text-xs font-label outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
              r === value
                ? "border-accent bg-accent-soft text-accent-text"
                : "border-border bg-surface-raised text-text hover:bg-surface-hover",
            )}
          >
            {t(`providers.region.${r}`)}
          </button>
        ))}
      </div>
      <p className="text-xs text-text-muted">{t("providers.region.hint")}</p>
    </div>
  );
}
