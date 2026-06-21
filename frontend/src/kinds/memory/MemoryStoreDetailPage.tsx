// frontend/src/kinds/memory/MemoryStoreDetailPage.tsx
//
// Memory store detail surface (spec 007 redesign): a back link + header (scope
// + metric badges + Clear all), a recall box, and a fact TREE on the left with
// a rendered preview/editor on the right (mirrors the KB detail page). Memory
// is AI-authored — agents write via the MCP `remember` tool; the UI lets humans
// CORRECT existing facts (edit the Markdown / delete), not add new ones.
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { translateApiError } from "@/lib/api/errors";
import { usePageClamp } from "@/lib/hooks/usePagedList";
import {
  clearFacts,
  deleteFact,
  getFact,
  getMemoryStore,
  getMemoryStoreMetrics,
  listFacts,
  storeDisplayName,
  recall,
  type FactOut,
  type RecallResponse,
} from "./api";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { MemoryDetailHeader } from "./MemoryDetailHeader";
import { MemoryRenameDialog } from "./MemoryRenameDialog";
import { MemoryFactTree } from "./MemoryFactTree";
import { MemoryFactViewer } from "./MemoryFactViewer";
import { MemoryRecallPanel } from "./MemoryRecallPanel";

// Facts are paged so a large (MCP-grown) store doesn't load all at once; the
// tree uses page-based pagination (server offset) below the list.
const DEFAULT_FACTS_PAGE_SIZE = 50;

export function MemoryStoreDetailPage() {
  const { t } = useTranslation();
  const store = useParams<{ name: string }>().name ?? "";
  const qc = useQueryClient();

  const [query, setQuery] = useState("");
  const [recallResult, setRecallResult] = useState<RecallResponse | null>(null);

  const [selected, setSelected] = useState<FactOut | null>(null);

  // Styled confirmation dialogs replace native window.confirm for the two
  // destructive actions (delete a fact, clear the whole store).
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);

  const [factPage, setFactPage] = useState(1);
  const [factPageSize, setFactPageSize] = useState(DEFAULT_FACTS_PAGE_SIZE);
  // A smaller page size can shrink the result set: reset to page 1.
  useEffect(() => {
    setFactPage(1);
  }, [factPageSize]);
  const factsQuery = useQuery({
    queryKey: ["memory-facts", store, factPage, factPageSize],
    queryFn: () => listFacts(store, factPageSize, (factPage - 1) * factPageSize),
    enabled: Boolean(store),
    // Keep the prior page's facts + total while the next page loads, so the page
    // count doesn't transiently read as 1 and trip the clamp during a forward nav.
    placeholderData: keepPreviousData,
  });
  const factTotal = factsQuery.data?.total ?? 0;
  const factPageCount = Math.max(1, Math.ceil(factTotal / factPageSize));
  // Pull the page back into range when the total shrinks (last page emptied).
  usePageClamp(factPage, factPageCount, setFactPage);

  // --- recall mode -----------------------------------------------------------
  // Running a recall filters the left tree to the matched facts and opens the
  // top hit highlighted; clearing the search box returns to the full paged list.
  const recalling = recallResult !== null;
  // Unique hit fact ids in rank order (a fact can match via several chunks).
  const hitIds = recallResult ? [...new Set(recallResult.hits.map((h) => h.id))] : [];
  // Recall returns only ranked snippets; fetch the full facts so the rows
  // (name + actor badge) and the viewer (full body) render like normal mode.
  const recallFactsQuery = useQuery({
    queryKey: ["memory-recall-facts", store, hitIds],
    queryFn: async () => {
      const facts = await Promise.all(hitIds.map((id) => getFact(store, id).catch(() => null)));
      return facts.filter((f): f is FactOut => f !== null);
    },
    enabled: recalling && hitIds.length > 0,
  });
  const recallFacts = recallFactsQuery.data ?? [];
  const recallLoading = recalling && hitIds.length > 0 && recallFactsQuery.isPending;
  // Auto-select the top hit when a recall resolves so its match opens highlighted.
  useEffect(() => {
    const facts = recallFactsQuery.data;
    if (recalling && facts && facts.length > 0) setSelected(facts[0]);
  }, [recallFactsQuery.data, recalling]);

  const metricsQuery = useQuery({
    queryKey: ["memory-metrics", store],
    queryFn: () => getMemoryStoreMetrics(store),
    enabled: Boolean(store),
  });
  const storeQuery = useQuery({
    queryKey: ["memory-store", store],
    queryFn: () => getMemoryStore(store),
    enabled: Boolean(store),
  });
  // Readable identity for user-facing strings: a user-set label (FR-017c), else
  // the project-dir basename (FR-017a), else the raw store name.
  const storeLabel = (storeQuery.data && storeDisplayName(storeQuery.data)) ?? store;

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["memory-facts", store] });
    void qc.invalidateQueries({ queryKey: ["memory-metrics", store] });
  };

  // Keep the selected fact in sync with the freshly-loaded list when it's on the
  // current page; otherwise (it's on another page) keep showing the captured
  // selection so paging the tree doesn't blank the viewer.
  const sourceFacts = recalling ? recallFacts : (factsQuery.data?.facts ?? []);
  const liveSelected = selected
    ? (sourceFacts.find((f) => f.id === selected.id) ?? selected)
    : null;

  const del = useMutation({
    mutationFn: (id: string) => deleteFact(store, id),
    onSuccess: () => {
      setSelected(null);
      setRecallResult(null); // a delete returns to the full list (no stale hit rows)
      invalidate();
    },
  });
  const recallM = useMutation({
    mutationFn: () => recall(store, query, { topK: 5 }),
    onSuccess: (data) => setRecallResult(data),
  });
  const clear = useMutation({
    mutationFn: () => clearFacts(store),
    onSuccess: () => {
      setSelected(null);
      invalidate();
    },
  });

  const selectFact = (f: FactOut) => setSelected(f);
  const onQueryChange = (value: string) => {
    setQuery(value);
    if (!value) setRecallResult(null); // clearing the search box exits recall mode
  };
  const confirmDelete = () => {
    if (!liveSelected) return;
    setDeleteOpen(true);
  };
  const confirmClear = () => setClearOpen(true);

  const loadError = factsQuery.error ?? metricsQuery.error;

  return (
    <div className="space-y-6 p-6">
      <MemoryDetailHeader
        store={store}
        storeResource={storeQuery.data}
        metrics={metricsQuery.data}
        isClearPending={clear.isPending}
        onClearAll={confirmClear}
        onRename={() => setRenameOpen(true)}
      />

      {loadError ? (
        <p className="text-sm text-destructive" role="alert">
          {translateApiError(t, loadError)}
        </p>
      ) : null}

      <MemoryRecallPanel
        query={query}
        error={recallM.error}
        isPending={recallM.isPending}
        onQueryChange={onQueryChange}
        onRecall={() => recallM.mutate()}
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(220px,300px)_1fr]">
        <MemoryFactTree
          facts={recalling ? { facts: recallFacts, total: recallFacts.length } : factsQuery.data}
          selectedId={liveSelected?.id ?? null}
          isLoading={recalling ? recallLoading : factsQuery.isPending}
          hidePagination={recalling}
          emptyLabel={recalling ? t("memory.detail.noMatches") : undefined}
          page={factPage}
          pageCount={factPageCount}
          pageSize={factPageSize}
          total={recalling ? recallFacts.length : factTotal}
          onPageChange={setFactPage}
          onPageSizeChange={setFactPageSize}
          onSelect={selectFact}
        />
        <MemoryFactViewer
          fact={liveSelected ?? undefined}
          initialQuery={recalling ? query : ""}
          isDeletePending={del.isPending}
          onDelete={confirmDelete}
        />
      </div>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("memory.detail.deleteTitle")}
        description={t("memory.detail.deleteConfirm", { name: liveSelected?.name || "fact" })}
        confirmLabel={del.isPending ? t("common.deleting") : t("common.delete")}
        pending={del.isPending}
        onConfirm={() => {
          if (liveSelected) {
            del.mutate(liveSelected.id, { onSuccess: () => setDeleteOpen(false) });
          }
        }}
      />

      <ConfirmDialog
        open={clearOpen}
        onOpenChange={setClearOpen}
        title={t("memory.detail.clearTitle")}
        description={t("memory.detail.clearConfirm", { store: storeLabel })}
        confirmLabel={t("memory.detail.clearAll")}
        pending={clear.isPending}
        onConfirm={() => clear.mutate(undefined, { onSuccess: () => setClearOpen(false) })}
      />

      <MemoryRenameDialog
        open={renameOpen}
        onOpenChange={setRenameOpen}
        store={store}
        currentLabel={storeQuery.data?.label ?? null}
      />
    </div>
  );
}
