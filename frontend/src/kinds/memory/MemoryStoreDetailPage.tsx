// frontend/src/kinds/memory/MemoryStoreDetailPage.tsx
//
// Memory store detail surface (spec 007 redesign): a back link + header (scope
// + metric badges + an "Add fact" button that opens a dialog), a recall box
// with a keyword/vector mode toggle, and a fact list with inline edit, delete,
// and "Clear all". No llm_provider anywhere — facts are written directly.
//
// This page is the composing container: it owns all state, queries, and
// mutations, and delegates rendering to cohesive child panels.
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { translateApiError } from "@/lib/api/errors";
import {
  addFact,
  clearFacts,
  deleteFact,
  getMemoryStore,
  getMemoryStoreMetrics,
  listFacts,
  recall,
  updateFact,
  type RecallResponse,
  type RetrievalMode,
} from "./api";
import { MemoryAddFactDialog } from "./MemoryAddFactDialog";
import { MemoryDetailHeader } from "./MemoryDetailHeader";
import { MemoryFactList } from "./MemoryFactList";
import { MemoryRecallPanel } from "./MemoryRecallPanel";

export function MemoryStoreDetailPage() {
  const { t } = useTranslation();
  const params = useParams<{ name: string }>();
  const store = params.name ?? "";
  const qc = useQueryClient();

  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<RetrievalMode>("keyword");
  const [recallResult, setRecallResult] = useState<RecallResponse | null>(null);

  // Add-fact dialog
  const [addOpen, setAddOpen] = useState(false);
  const [text, setText] = useState("");
  const [factName, setFactName] = useState("");
  const [factDescription, setFactDescription] = useState("");
  const [factType, setFactType] = useState("");

  // Inline edit
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  const factsQuery = useQuery({
    queryKey: ["memory-facts", store],
    queryFn: () => listFacts(store, 100, 0),
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

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["memory-facts", store] });
    void qc.invalidateQueries({ queryKey: ["memory-metrics", store] });
  };

  const add = useMutation({
    mutationFn: () =>
      addFact(store, {
        text: text.trim(),
        name: factName.trim() || null,
        description: factDescription.trim() || null,
        type: factType.trim() || null,
      }),
    onSuccess: () => {
      setText("");
      setFactName("");
      setFactDescription("");
      setFactType("");
      setAddOpen(false);
      invalidate();
    },
  });

  const del = useMutation({
    mutationFn: (id: string) => deleteFact(store, id),
    onSuccess: invalidate,
  });

  const upd = useMutation({
    mutationFn: (input: { id: string; text: string }) =>
      updateFact(store, input.id, { text: input.text }),
    onSuccess: () => {
      setEditingId(null);
      setEditText("");
      invalidate();
    },
  });

  const recallM = useMutation({
    mutationFn: () => recall(store, query, { topK: 5, mode }),
    onSuccess: (data) => setRecallResult(data),
  });

  const clear = useMutation({
    mutationFn: () => clearFacts(store),
    onSuccess: invalidate,
  });

  // Surface failure of the primary list/metrics queries (e.g. a 404 store)
  // instead of rendering blank sections.
  const loadError = factsQuery.error ?? metricsQuery.error;

  return (
    <div className="space-y-6 p-6">
      <MemoryDetailHeader
        store={store}
        storeResource={storeQuery.data}
        metrics={metricsQuery.data}
        onAddFact={() => setAddOpen(true)}
      />

      <MemoryAddFactDialog
        open={addOpen}
        onOpenChange={(o) => {
          if (!o) add.reset();
          setAddOpen(o);
        }}
        text={text}
        name={factName}
        description={factDescription}
        type={factType}
        error={add.error}
        isPending={add.isPending}
        onTextChange={setText}
        onNameChange={setFactName}
        onDescriptionChange={setFactDescription}
        onTypeChange={setFactType}
        onSubmit={() => add.mutate()}
      />

      {loadError ? (
        <p className="text-sm text-destructive" role="alert">
          {translateApiError(t, loadError)}
        </p>
      ) : factsQuery.isPending || metricsQuery.isPending ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
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

      <MemoryFactList
        store={store}
        facts={factsQuery.data}
        editingId={editingId}
        editText={editText}
        isClearPending={clear.isPending}
        isUpdatePending={upd.isPending}
        isDeletePending={del.isPending}
        onClearAll={() => clear.mutate()}
        onStartEdit={(f) => {
          setEditingId(f.id);
          setEditText(f.text);
        }}
        onDelete={(id) => del.mutate(id)}
        onEditTextChange={setEditText}
        onSaveEdit={(id) => upd.mutate({ id, text: editText })}
        onCancelEdit={() => {
          setEditingId(null);
          setEditText("");
        }}
      />
    </div>
  );
}
