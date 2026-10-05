// src/components/secret/SecretsList.tsx — the Secrets page's list pane: search and status, then the secrets.
//
// Search (name, description, reference) and the status segments (All · In use · Not used) live in
// the URL (`?q=` `?status=`) and are applied to every secret at once. Ticking a secret swaps them
// for the selection bar (bulk delete). A row opens `/secrets/<ref>` in the pane beside it.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ListSelectAll } from "@/components/ListSelectAll";
import { ListLoadError, ListLoadingRows, ListNoMatch } from "@/components/ListPaneStates";
import { Button } from "@/components/ui/button";
import { SearchInput } from "@/components/SearchInput";
import { Segmented } from "@/components/ui/segmented";
import type { SecretRef } from "@/lib/api/secret";
import { useSecretListState } from "@/lib/hooks/useSecretListState";
import { STATUSES, type SecretStatus } from "@/lib/secrets/listState";
import { SecretListRow } from "./SecretListRow";
import { SecretsBulkBar } from "./SecretsBulkBar";
import { decorate, defaultOrder, filterItems } from "./secretListView";

/** How many secrets the list renders before "Load more"; search and filters cover them all. */
const BATCH = 50;

interface Props {
  rows: SecretRef[];
  isLoading: boolean;
  error?: unknown;
  onRetry?: () => void;
  /** The open secret's ref. */
  selectedRef: string | null;
}

export function SecretsList({ rows, isLoading, error, onRetry, selectedRef }: Props) {
  const { t } = useTranslation();
  const { search } = useLocation();
  const { state, update, clear } = useSecretListState();
  const [pickedRefs, setPickedRefs] = useState<ReadonlySet<string>>(new Set());
  const [limit, setLimit] = useState(BATCH);

  const items = useMemo(() => decorate(rows, t("secrets.unnamed")), [rows, t]);
  const shown = useMemo(() => defaultOrder(filterItems(items, state)), [items, state]);
  // A secret that has gone from the list (deleted, or filtered out) is no longer ticked.
  const picked = useMemo(() => shown.filter((i) => pickedRefs.has(i.row.ref)), [shown, pickedRefs]);
  // A new search or status starts again at the first batch.
  useEffect(() => setLimit(BATCH), [state.q, state.status]);
  const toggle = useCallback((ref: string, on: boolean) => {
    setPickedRefs((prev) => {
      const next = new Set(prev);
      if (on) next.add(ref);
      else next.delete(ref);
      return next;
    });
  }, []);
  const clearPicked = useCallback(() => setPickedRefs(new Set()), []);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-col gap-2.5 px-3 pb-2.5 pt-3.5">
        {picked.length > 0 ? (
          <SecretsBulkBar selected={picked} total={shown.length} onClear={clearPicked} />
        ) : (
          <>
            <SearchInput
              value={state.q}
              onChange={(q) => update({ q })}
              placeholder={t("secrets.search")}
              ariaLabel={t("secrets.search")}
              shortcut="/"
            />
            <Segmented<SecretStatus>
              label={t("secrets.filters.status.label")}
              value={state.status}
              onChange={(status) => update({ status })}
              options={STATUSES.map((s) => ({ value: s, label: t(`secrets.filters.status.${s}`) }))}
            />
          </>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        <ListSelectAll
          count={picked.length}
          total={shown.length}
          onChange={(all) => setPickedRefs(all ? new Set(shown.map((i) => i.row.ref)) : new Set())}
        />
        {error ? (
          <ListLoadError kind="secrets" error={error} onRetry={() => onRetry?.()} />
        ) : isLoading ? (
          <ListLoadingRows />
        ) : shown.length === 0 ? (
          <ListNoMatch kind="secrets" query={state.q} onClear={clear} />
        ) : (
          <ul className="flex flex-col gap-0.5" aria-label={t("secrets.title")}>
            {shown.slice(0, limit).map((item) => (
              <SecretListRow
                key={item.row.ref}
                item={item}
                to={`/secrets/${encodeURIComponent(item.row.ref)}${search}`}
                current={item.row.ref === selectedRef}
                selecting={picked.length > 0}
                checked={pickedRefs.has(item.row.ref)}
                onCheckedChange={(on) => toggle(item.row.ref, on)}
              />
            ))}
          </ul>
        )}
        {shown.length > limit ? (
          <div className="flex flex-col items-center gap-1.5 px-2 pt-3 text-xs text-text-muted">
            {t("pagination.showing", { shown: limit, total: shown.length })}
            <Button size="sm" variant="outline" onClick={() => setLimit(limit + BATCH)}>
              {t("pagination.loadMore", { count: BATCH })}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
