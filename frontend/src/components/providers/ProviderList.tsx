// src/components/providers/ProviderList.tsx — the list pane: a filter, one row per provider.
//
// The filter matches the name, title, endpoint and description. The label
// "Fallback order ?" says what the order is; there is no count. There is no
// per-row switch or reach control here: activation is per agent (its Model
// tab), and reach is changed on the provider's own header. The order is
// fallback priority (spec provider-switching "Order providers, and fail over
// in that order"): each row has a drag handle, and a move saves the whole
// order. Reordering waits while a filter hides rows.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { HelpTip } from "@/components/HelpTip";
import { ListLoadError, ListLoadingRows, ListNoMatch } from "@/components/ListPaneStates";
import { SearchInput } from "@/components/SearchInput";
import type { Provider } from "@/lib/api/providers";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { searchableName } from "@/lib/resourceTitle";
import { useReorderProviders } from "@/lib/hooks/useProviderFallback";
import { ProviderListRow } from "./ProviderListRow";
import { ReorderHandle, moved } from "./ReorderHandle";

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
  const [dragging, setDragging] = useState<number | null>(null);
  const reorder = useReorderProviders();
  const needle = filter.trim().toLowerCase();
  const rows = needle
    ? providers.filter((p) =>
        `${searchableName(p)} ${p.base_url} ${p.description ?? ""}`.toLowerCase().includes(needle),
      )
    : providers;
  const uids = providers.map((p) => p.uid);
  const canReorder = !needle && providers.length > 1 && !reorder.isPending;
  const move = (from: number, to: number) => {
    if (from === to || to < 0 || to >= uids.length) return;
    reorder.mutate(moved(uids, from, to));
  };

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
          <HelpTip label={t("providers.list.orderHelpLabel")} className="ml-1.5">
            {t("providers.list.orderHelp")}
          </HelpTip>
        </div>
        {error ? (
          <ListLoadError kind="providers" error={error} onRetry={() => onRetry?.()} />
        ) : isLoading ? (
          <ListLoadingRows />
        ) : rows.length === 0 ? (
          <ListNoMatch kind="providers" query={filter} onClear={() => setFilter("")} />
        ) : (
          rows.map((p, index) => (
            <div
              key={p.uid}
              onDragOver={(e) => {
                if (dragging !== null) e.preventDefault();
              }}
              onDrop={(e) => {
                e.preventDefault();
                if (dragging !== null) move(dragging, index);
                setDragging(null);
              }}
              onDragEnd={() => setDragging(null)}
              className={dragging === index ? "opacity-50" : undefined}
            >
              <ProviderListRow
                provider={p}
                use={usageOf(p)}
                selected={p.uid === selectedUid}
                problem={p.uid === selectedUid ? selectedProblem : null}
                handle={
                  <ReorderHandle
                    name={p.name}
                    disabled={!canReorder}
                    onDragStart={() => setDragging(index)}
                    onMove={(delta) => move(index, index + delta)}
                  />
                }
              />
            </div>
          ))
        )}
      </nav>
    </div>
  );
}
