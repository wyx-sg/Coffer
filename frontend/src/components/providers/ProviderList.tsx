// src/components/providers/ProviderList.tsx — the list pane: a filter, the count, one row per provider.
//
// The filter matches the name, title, endpoint and description. There is no
// per-row switch or reach control here: activation is per agent (its Model
// tab), and reach is changed on the provider's own header.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { SearchInput } from "@/components/SearchInput";
import { Skeleton } from "@/components/ui/skeleton";
import type { Provider } from "@/lib/api/providers";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { searchableName } from "@/lib/resourceTitle";
import { ProviderListRow } from "./ProviderListRow";

interface Props {
  providers: Provider[];
  isLoading: boolean;
  selectedUid: string | undefined;
  usageOf: (provider: Provider) => ProviderUse;
  /** The open provider's rejected-key status, when its probe found one. */
  selectedRejected?: string | null;
}

export function ProviderList({
  providers,
  isLoading,
  selectedUid,
  usageOf,
  selectedRejected,
}: Props) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("");
  const needle = filter.trim().toLowerCase();
  const rows = needle
    ? providers.filter((p) =>
        `${searchableName(p)} ${p.base_url} ${p.description ?? ""}`.toLowerCase().includes(needle),
      )
    : providers;

  return (
    <div className="flex min-h-0 flex-col gap-3.5 px-2 py-3">
      <SearchInput
        value={filter}
        onChange={setFilter}
        placeholder={t("providers.list.filter")}
        ariaLabel={t("providers.list.filter")}
        className="px-0.5"
      />
      <nav aria-label={t("providers.list.heading")} className="flex min-h-0 flex-col gap-px">
        <div className="flex items-center px-2.5 pb-1 text-2xs font-semibold text-text-muted">
          {t("providers.list.heading")}
          <span className="ml-auto font-book">{providers.length}</span>
        </div>
        {isLoading ? (
          <div className="flex flex-col gap-2 px-2.5" aria-busy="true">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : rows.length === 0 ? (
          <p className="px-2.5 py-2 text-xs text-text-muted">{t("providers.list.noMatch")}</p>
        ) : (
          rows.map((p) => (
            <ProviderListRow
              key={p.uid}
              provider={p}
              use={usageOf(p)}
              selected={p.uid === selectedUid}
              rejected={p.uid === selectedUid ? selectedRejected : undefined}
            />
          ))
        )}
      </nav>
    </div>
  );
}
