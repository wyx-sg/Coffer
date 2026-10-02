// src/components/providers/ModelsToolbar.tsx — the Models card's sticky filter row: search and the type filter.
import { useTranslation } from "react-i18next";

import { SearchInput } from "@/components/SearchInput";
import { Segmented } from "@/components/ui/segmented";
import type { Modality } from "@/lib/api/providers";

interface Props {
  query: string;
  onQuery: (q: string) => void;
  types: readonly Modality[];
  type: Modality | "all";
  onType: (t: Modality | "all") => void;
}

export function ModelsToolbar({ query, onQuery, types, type, onType }: Props) {
  const { t } = useTranslation();
  const options = (["all", ...types] as const).map((m) => ({
    value: m,
    label: m === "all" ? t("providers.models.allTypes") : t(`providers.modalities.${m}`),
  }));
  return (
    // Sticky under the card header while the detail pane scrolls; it bleeds to
    // the card's edges so rows slide under a solid band.
    <div className="sticky top-0 z-sticky -mx-4 flex flex-wrap items-center gap-2 bg-surface-raised px-4 py-2.5">
      <SearchInput
        value={query}
        onChange={onQuery}
        placeholder={t("providers.models.search")}
        ariaLabel={t("providers.models.search")}
        className="w-56"
      />
      <Segmented
        label={t("providers.models.typeFilter")}
        value={type}
        options={options}
        onChange={onType}
      />
    </div>
  );
}
