// src/components/secret/SecretsList.tsx — the Secrets page's list pane: search and status, then the secrets.
//
// The same shape as the other library lists (MCP servers, Skills): a filter box, a "Status: All"
// filter chip under it, then the secrets grouped In use · Not used. Search (name, description,
// reference) and status live in the URL (`?q=` `?status=`) and are applied to every secret at
// once. Ticking a secret swaps them for the selection bar (bulk delete). A row opens
// `/secrets/<ref>` in the pane beside it.
import { useCallback, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ListSelectAll } from "@/components/ListSelectAll";
import { ListLoadError, ListLoadingRows, ListNoMatch } from "@/components/ListPaneStates";
import { LoadMoreSentinel } from "@/components/ui/load-more";
import { SearchInput } from "@/components/SearchInput";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { SecretRef } from "@/lib/api/secret";
import { useGrowingList } from "@/lib/hooks/useGrowingList";
import { useSecretListState } from "@/lib/hooks/useSecretListState";
import { STATUSES, type SecretStatus } from "@/lib/secrets/listState";
import { SecretListRow } from "./SecretListRow";
import { SecretsBulkBar } from "./SecretsBulkBar";
import { decorate, defaultOrder, filterItems, type SecretItem } from "./secretListView";

/** The list's groups, in order: what something uses, then what nothing does. */
const GROUPS = ["inUse", "unused"] as const;
const groupOf = (i: SecretItem) => (i.row.unreferenced ? "unused" : "inUse");

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

  const items = useMemo(() => decorate(rows, t("secrets.unnamed")), [rows, t]);
  // Grouped first, so the list grows in the order it is shown.
  const shown = useMemo(() => {
    const ordered = defaultOrder(filterItems(items, state));
    return GROUPS.flatMap((g) => ordered.filter((i) => groupOf(i) === g));
  }, [items, state]);
  const grow = useGrowingList(shown, `${state.q}\u241f${state.status}`);
  // A secret that has gone from the list (deleted, or filtered out) is no longer ticked.
  const picked = useMemo(() => shown.filter((i) => pickedRefs.has(i.row.ref)), [shown, pickedRefs]);
  // A new search or status starts again at the first batch.
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
            />
            <div className="flex items-center gap-2">
              <Select
                value={state.status}
                onValueChange={(status) => update({ status: status as SecretStatus })}
              >
                <SelectTrigger
                  className="h-control-sm w-auto max-w-56 gap-1.5 text-xs"
                  aria-label={t("secrets.filters.status.label")}
                >
                  <span className="text-text-muted">{t("secrets.filters.status.label")}:</span>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUSES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {t(`secrets.filters.status.${s}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
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
          <div role="group" aria-label={t("secrets.title")}>
            {GROUPS.map((group) => {
              const rows = grow.shown.filter((i) => groupOf(i) === group);
              if (rows.length === 0) return null;
              return (
                <section
                  key={group}
                  className="mb-3"
                  aria-label={t(`secrets.filters.status.${group}`)}
                >
                  <h2 className="flex items-center px-2.5 pb-1 text-2xs font-semibold text-text-muted">
                    {t(`secrets.filters.status.${group}`)}
                  </h2>
                  <ul className="flex flex-col gap-0.5">
                    {rows.map((item) => (
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
                </section>
              );
            })}
          </div>
        )}
        <LoadMoreSentinel active={grow.hasMore} onVisible={grow.more} version={grow.shown.length} />
      </div>
    </div>
  );
}
