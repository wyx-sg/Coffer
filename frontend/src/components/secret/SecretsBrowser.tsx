// src/components/secret/SecretsBrowser.tsx — the Secrets list: filters (or the selection bar), then the table.
//
// Status and search live in the URL, the sort too (`?sort=last_used`); they are applied to every
// secret at once and only a batch is rendered. Ticking a secret swaps the filter row for the
// selection bar.
import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { FilterRow } from "@/components/filters";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { useSecretListState } from "@/lib/hooks/useSecretListState";
import { useSortParam } from "@/lib/hooks/useSortParam";
import { isFiltered, STATUSES, type SecretStatus } from "@/lib/secrets/listState";
import type { SecretRef } from "@/lib/api/secret";
import type { SecretRowAction } from "./SecretRowMenu";
import { SecretsBulkBar } from "./SecretsBulkBar";
import { SecretsTable } from "./SecretsTable";
import { decorate, defaultOrder, filterItems } from "./secretListView";

interface Props {
  rows: SecretRef[];
  /** Refs whose new value, or whose adding, waits for approval. */
  waiting: ReadonlySet<string>;
  isLoading: boolean;
  onAction: (action: SecretRowAction, row: SecretRef) => void;
}

export function SecretsBrowser({ rows, waiting, isLoading, onAction }: Props) {
  const { t } = useTranslation();
  const { state, update, clear } = useSecretListState();
  const [sort, setSort] = useSortParam();
  const [selectedRefs, setSelectedRefs] = useState<ReadonlySet<string>>(new Set());

  const items = useMemo(() => decorate(rows, waiting), [rows, waiting]);
  const shown = useMemo(() => defaultOrder(filterItems(items, state)), [items, state]);
  // A secret that has gone from the list (deleted, or filtered out by a reload) is no longer ticked.
  const selected = useMemo(
    () => shown.filter((i) => selectedRefs.has(i.row.ref)),
    [shown, selectedRefs],
  );

  const toggle = useCallback((ref: string, on: boolean) => {
    setSelectedRefs((prev) => {
      const next = new Set(prev);
      if (on) next.add(ref);
      else next.delete(ref);
      return next;
    });
  }, []);
  const toggleAll = useCallback(
    (on: boolean) => setSelectedRefs(on ? new Set(shown.map((i) => i.row.ref)) : new Set()),
    [shown],
  );
  const clearSelection = useCallback(() => setSelectedRefs(new Set()), []);
  const filtered = isFiltered(state);

  return (
    <div className="space-y-3">
      {selected.length > 0 ? (
        <SecretsBulkBar selected={selected} total={shown.length} onClear={clearSelection} />
      ) : (
        <FilterRow
          segmented={
            <Segmented<SecretStatus>
              label={t("secrets.filters.status.label")}
              value={state.status}
              onChange={(status) => update({ status })}
              options={STATUSES.map((s) => ({ value: s, label: t(`secrets.filters.status.${s}`) }))}
            />
          }
          search={{
            value: state.q,
            onChange: (q) => update({ q }),
            placeholder: t("secrets.search"),
            shortcut: "/",
          }}
          active={filtered}
          onClear={clear}
        />
      )}
      <SecretsTable
        // A new filter starts again at the first batch.
        key={`${state.q}|${state.status}`}
        items={shown}
        sort={sort}
        onSortChange={setSort}
        selected={selectedRefs}
        onToggle={toggle}
        onToggleAll={toggleAll}
        isLoading={isLoading}
        emptyMessage={t("secrets.noMatch")}
        emptyAction={
          filtered ? (
            <Button variant="outline" size="sm" onClick={clear}>
              {t("filters.clearAll")}
            </Button>
          ) : undefined
        }
        onAction={onAction}
      />
    </div>
  );
}
