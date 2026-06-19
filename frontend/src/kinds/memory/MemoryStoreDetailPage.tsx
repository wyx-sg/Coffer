// frontend/src/kinds/memory/MemoryStoreDetailPage.tsx
//
// Memory store detail surface (spec 007 redesign): a back link + header (scope
// + metric badges + Clear all), a recall box, and a fact TREE on the left with
// a rendered preview/editor on the right (mirrors the KB detail page). Memory
// is AI-authored — agents write via the MCP `remember` tool; the UI lets humans
// CORRECT existing facts (edit the Markdown / delete), not add new ones.
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { translateApiError } from "@/lib/api/errors";
import {
  clearFacts,
  deleteFact,
  getMemoryStore,
  getMemoryStoreMetrics,
  listFacts,
  storeDisplayName,
  recall,
  type FactOut,
  type RecallResponse,
  type RetrievalMode,
} from "./api";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { MemoryDetailHeader } from "./MemoryDetailHeader";
import { MemoryRenameDialog } from "./MemoryRenameDialog";
import { MemoryFactTree } from "./MemoryFactTree";
import { MemoryFactViewer } from "./MemoryFactViewer";
import { MemoryRecallPanel } from "./MemoryRecallPanel";

// Facts are paged so a large (MCP-grown) store doesn't load all at once; the
// tree shows a "Load more" affordance once more facts exist than are loaded.
const FACTS_PAGE_SIZE = 100;

export function MemoryStoreDetailPage() {
  const { t } = useTranslation();
  const store = useParams<{ name: string }>().name ?? "";
  const qc = useQueryClient();

  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<RetrievalMode>("keyword");
  const [recallResult, setRecallResult] = useState<RecallResponse | null>(null);

  const [selected, setSelected] = useState<FactOut | null>(null);

  // Styled confirmation dialogs replace native window.confirm for the two
  // destructive actions (delete a fact, clear the whole store).
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);

  const [factLimit, setFactLimit] = useState(FACTS_PAGE_SIZE);
  const factsQuery = useQuery({
    queryKey: ["memory-facts", store, factLimit],
    queryFn: () => listFacts(store, factLimit, 0),
    enabled: Boolean(store),
  });
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

  // Keep the selected fact in sync with the freshly-loaded list.
  const liveSelected = selected
    ? (factsQuery.data?.facts.find((f) => f.id === selected.id) ?? null)
    : null;

  const del = useMutation({
    mutationFn: (id: string) => deleteFact(store, id),
    onSuccess: () => {
      setSelected(null);
      invalidate();
    },
  });
  const recallM = useMutation({
    mutationFn: () => recall(store, query, { topK: 5, mode }),
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
        mode={mode}
        result={recallResult}
        error={recallM.error}
        isPending={recallM.isPending}
        onQueryChange={setQuery}
        onModeChange={setMode}
        onRecall={() => recallM.mutate()}
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(220px,300px)_1fr]">
        <MemoryFactTree
          facts={factsQuery.data}
          selectedId={liveSelected?.id ?? null}
          isLoading={factsQuery.isPending}
          isLoadingMore={factsQuery.isFetching}
          onLoadMore={() => setFactLimit((n) => n + FACTS_PAGE_SIZE)}
          onSelect={selectFact}
        />
        <MemoryFactViewer
          fact={liveSelected ?? undefined}
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
