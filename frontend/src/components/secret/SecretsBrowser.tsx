// src/components/secret/SecretsBrowser.tsx — the Secrets list: filters (or the selection bar), then the table or the by-owner groups.
//
// Filters, sort and view live in the URL; the filters and the sort are applied to every secret
// at once and only a batch is rendered. Ticking a secret swaps the filter row for the selection bar.
import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { useSecretListState } from "@/lib/hooks/useSecretListState";
import type { SortKey } from "@/lib/secrets/listState";
import type { SecretRef } from "@/lib/api/secret";
import type { SecretRowAction } from "./SecretRowMenu";
import { SecretsBulkBar } from "./SecretsBulkBar";
import { SecretsBulkDelete } from "./SecretsBulkDelete";
import { SecretsByOwner } from "./SecretsByOwner";
import { SecretsFilterRow } from "./SecretsFilterRow";
import { SecretsTable } from "./SecretsTable";
import {
  decorate,
  isDeletable,
  matchesStatus,
  searchAndKind,
  sortItems,
  statusCounts,
} from "./secretListView";

interface Props {
  rows: SecretRef[];
  /** Refs whose new value, or whose adding, waits for approval. */
  waiting: ReadonlySet<string>;
  /** Refs a person refused to send somewhere. */
  refused: ReadonlySet<string>;
  isLoading: boolean;
  onAction: (action: SecretRowAction, row: SecretRef) => void;
}

export function SecretsBrowser({ rows, waiting, refused, isLoading, onAction }: Props) {
  const { t } = useTranslation();
  const { state, update } = useSecretListState();
  const [selectedRefs, setSelectedRefs] = useState<ReadonlySet<string>>(new Set());

  const items = useMemo(() => decorate(rows, waiting, refused), [rows, waiting, refused]);
  const scoped = useMemo(() => searchAndKind(items, state), [items, state]);
  const counts = useMemo(() => statusCounts(scoped), [scoped]);
  const shown = useMemo(
    () =>
      sortItems(
        scoped.filter((i) => matchesStatus(i, state.status)),
        state,
      ),
    [scoped, state],
  );
  const unused = useMemo(() => items.filter((i) => i.row.unreferenced && isDeletable(i)), [items]);
  // A secret that has gone from the list (deleted, or filtered out by a reload) is no longer ticked.
  const selected = useMemo(
    () => items.filter((i) => selectedRefs.has(i.row.ref)),
    [items, selectedRefs],
  );

  const toggle = useCallback((ref: string, on: boolean) => {
    setSelectedRefs((prev) => {
      const next = new Set(prev);
      if (on) next.add(ref);
      else next.delete(ref);
      return next;
    });
  }, []);
  const sortBy = (column: SortKey) =>
    update(
      state.sort === column
        ? { dir: state.dir === "asc" ? "desc" : "asc" }
        : { sort: column, dir: "asc" },
    );
  const clear = () => setSelectedRefs(new Set());
  const allChecked = shown.length > 0 && shown.every((i) => selectedRefs.has(i.row.ref));
  const emptyMessage = t("secrets.noMatch");

  return (
    <div className="space-y-3">
      {selected.length > 0 ? (
        <SecretsBulkBar
          selected={selected}
          allChecked={allChecked}
          onToggleAll={(on) =>
            setSelectedRefs(on ? new Set(shown.map((i) => i.row.ref)) : new Set())
          }
          onClear={clear}
        />
      ) : (
        <SecretsFilterRow
          state={state}
          counts={counts}
          onChange={update}
          trailing={
            unused.length > 0 ? (
              <SecretsBulkDelete items={unused} label={t("secrets.bulk.deleteUnused")} />
            ) : null
          }
        />
      )}
      {state.view === "owner" ? (
        <SecretsByOwner
          items={shown}
          state={state}
          selected={selectedRefs}
          onToggle={toggle}
          onAction={onAction}
          emptyMessage={emptyMessage}
        />
      ) : (
        <SecretsTable
          items={shown}
          state={state}
          onSort={sortBy}
          selected={selectedRefs}
          onToggle={toggle}
          isLoading={isLoading}
          emptyMessage={emptyMessage}
          onAction={onAction}
        />
      )}
    </div>
  );
}
