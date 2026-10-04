// src/components/providers/ProviderList.tsx — the list pane: a filter, one row per provider.
//
// The filter matches the name, title, endpoint and description. There is no
// count and no per-row switch or reach control here: activation is per agent
// (its Model tab), and reach is changed on the provider's own header. Rows
// come sorted by name.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ListLoadError, ListLoadingRows, ListNoMatch } from "@/components/ListPaneStates";
import { SearchInput } from "@/components/SearchInput";
import type { Provider } from "@/lib/api/providers";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { searchableName } from "@/lib/resourceTitle";
import { ProviderListRow } from "./ProviderListRow";

interface Props {
  providers: Provider[];
  isLoading: boolean;
  /** The list read failed: the pane shows the error block under the filter. */
  error?: unknown;
  onRetry?: () => void;
  selectedUid: string | undefined;
  usageOf: (provider: Provider) => ProviderUse;
  /** What the open provider's probe found wrong, when it did: its row says so in place of its sub-line. */
  selectedProblem?: "keyRejected" | "unreachable" | null;
}

export function ProviderList({
  providers,
  isLoading,
  error,
  onRetry,
  selectedUid,
  usageOf,
  selectedProblem,
}: Props) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("");
  const needle = filter.trim().toLowerCase();
  const rows = needle
    ? providers.filter((p) => searchableName(p).toLowerCase().includes(needle))
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
      <nav className="flex min-h-0 flex-col gap-px">
        {error ? (
          <ListLoadError kind="providers" error={error} onRetry={() => onRetry?.()} />
        ) : isLoading ? (
          <ListLoadingRows />
        ) : rows.length === 0 ? (
          <ListNoMatch kind="providers" query={filter} onClear={() => setFilter("")} />
        ) : (
          rows.map((p) => (
            <ProviderListRow
              key={p.uid}
              provider={p}
              use={usageOf(p)}
              selected={p.uid === selectedUid}
              problem={p.uid === selectedUid ? selectedProblem : null}
            />
          ))
        )}
      </nav>
    </div>
  );
}
