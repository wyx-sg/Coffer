// frontend/src/kinds/knowledge_base/KnowledgeBaseDetailPage.tsx
//
// KB detail surface (spec 006 redesign): metrics header, search box with a
// keyword/vector mode toggle, a grep box, a Reindex action, and a document
// list with per-doc Markdown edit (sets source_mode=edited), a source_mode
// badge, and delete. Uploads accept ANY format (converted to Markdown on the
// server). The KB is agent-read-only; all writes here are user-curated.
//
// This page is the composing container: it owns all state, queries, and
// mutations, and delegates rendering to cohesive child panels.
import { useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { translateApiError } from "@/lib/api/errors";
import {
  deleteDocument,
  editDocument,
  getDocument,
  getKnowledgeBaseMetrics,
  grepKnowledgeBase,
  ingestDocument,
  listDocuments,
  reindexKnowledgeBase,
  searchKnowledgeBase,
  type GrepResponse,
  type RetrievalMode,
  type SearchResponse,
} from "./api";
import { KnowledgeBaseDocumentList } from "./KnowledgeBaseDocumentList";
import { KnowledgeBaseGrepPanel } from "./KnowledgeBaseGrepPanel";
import { KnowledgeBaseMetricsHeader } from "./KnowledgeBaseMetricsHeader";
import { KnowledgeBaseSearchPanel } from "./KnowledgeBaseSearchPanel";

export function KnowledgeBaseDetailPage() {
  const { t } = useTranslation();
  const params = useParams<{ name: string }>();
  const name = params.name ?? "";
  const qc = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<RetrievalMode>("keyword");
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);

  const [pattern, setPattern] = useState("");
  const [grepResult, setGrepResult] = useState<GrepResponse | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  const docsQuery = useQuery({
    queryKey: ["kb-documents", name],
    queryFn: () => listDocuments(name, 50, 0),
    enabled: Boolean(name),
  });

  const metricsQuery = useQuery({
    queryKey: ["kb-metrics", name],
    queryFn: () => getKnowledgeBaseMetrics(name),
    enabled: Boolean(name),
  });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["kb-documents", name] });
    void qc.invalidateQueries({ queryKey: ["kb-metrics", name] });
  };

  const ingest = useMutation({
    mutationFn: (file: File) => ingestDocument(name, file, false),
    onSuccess: invalidate,
  });

  const del = useMutation({
    mutationFn: (id: string) => deleteDocument(name, id),
    onSuccess: invalidate,
  });

  const edit = useMutation({
    mutationFn: (input: { id: string; markdown: string }) =>
      editDocument(name, input.id, input.markdown),
    onSuccess: () => {
      setEditingId(null);
      setEditText("");
      invalidate();
    },
  });

  const reindex = useMutation({
    mutationFn: () => reindexKnowledgeBase(name),
    onSuccess: invalidate,
  });

  const search = useMutation({
    mutationFn: () => searchKnowledgeBase(name, query, { topK: 5, mode }),
    onSuccess: (data) => setSearchResult(data),
  });

  const grep = useMutation({
    mutationFn: () => grepKnowledgeBase(name, pattern, 100),
    onSuccess: (data) => setGrepResult(data),
  });

  const startEdit = useMutation({
    mutationFn: (id: string) => getDocument(name, id),
    onSuccess: (doc) => {
      setEditingId(doc.id);
      setEditText(doc.markdown);
    },
  });

  const handlePickFile = () => fileInputRef.current?.click();
  const handleFileChange: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const f = e.target.files?.[0];
    if (f) ingest.mutate(f);
    e.target.value = "";
  };

  // Surface failure of the primary list/metrics queries (e.g. a 404 store)
  // instead of rendering blank sections.
  const loadError = docsQuery.error ?? metricsQuery.error;

  return (
    <div className="space-y-6 p-6">
      <KnowledgeBaseMetricsHeader
        name={name}
        metrics={metricsQuery.data}
        reindexResult={reindex.data}
        isReindexPending={reindex.isPending}
        onReindex={() => reindex.mutate()}
      />

      {loadError ? (
        <p className="text-sm text-destructive" role="alert">
          {translateApiError(t, loadError)}
        </p>
      ) : docsQuery.isPending || metricsQuery.isPending ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : null}

      <KnowledgeBaseSearchPanel
        query={query}
        mode={mode}
        result={searchResult}
        error={search.error}
        isPending={search.isPending}
        onQueryChange={setQuery}
        onModeChange={setMode}
        onSearch={() => search.mutate()}
      />

      <KnowledgeBaseGrepPanel
        pattern={pattern}
        result={grepResult}
        error={grep.error}
        isPending={grep.isPending}
        onPatternChange={setPattern}
        onGrep={() => grep.mutate()}
      />

      <KnowledgeBaseDocumentList
        docs={docsQuery.data}
        ingestError={ingest.error}
        isIngestPending={ingest.isPending}
        editingId={editingId}
        editText={editText}
        isStartEditPending={startEdit.isPending}
        isDeletePending={del.isPending}
        isEditPending={edit.isPending}
        onPickFile={handlePickFile}
        onStartEdit={(id) => startEdit.mutate(id)}
        onDelete={(id) => del.mutate(id)}
        onEditTextChange={setEditText}
        onSaveEdit={(id) => edit.mutate({ id, markdown: editText })}
        onCancelEdit={() => {
          setEditingId(null);
          setEditText("");
        }}
      />
      <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileChange} />
    </div>
  );
}
