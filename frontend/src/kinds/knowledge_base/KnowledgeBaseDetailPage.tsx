// frontend/src/kinds/knowledge_base/KnowledgeBaseDetailPage.tsx
//
// KB detail surface (spec 006 redesign): metrics header, search box with a
// keyword/vector mode toggle, a grep box, Settings (post-creation config
// editing) + Reindex actions, and a document list with per-doc Markdown edit
// (sets source_mode=edited), a source_mode badge, reconvert, and delete.
// Uploads accept ANY format (converted to Markdown on the server); a
// duplicate-rejected upload can be retried with replace=true. The KB is
// agent-read-only; all writes here are user-curated.
//
// This page is the composing container: it owns all state, queries, and
// mutations, and delegates rendering to cohesive child panels.
import { useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";
import {
  deleteDocument,
  editDocument,
  getDocument,
  getKnowledgeBase,
  getKnowledgeBaseMetrics,
  grepKnowledgeBase,
  ingestDocument,
  listDocuments,
  reconvertDocument,
  reindexKnowledgeBase,
  searchKnowledgeBase,
  updateKnowledgeBaseConfig,
  type GrepResponse,
  type KnowledgeBaseConfigOut,
  type RetrievalMode,
  type SearchResponse,
} from "./api";
import { KnowledgeBaseDocumentList } from "./KnowledgeBaseDocumentList";
import { KnowledgeBaseGrepPanel } from "./KnowledgeBaseGrepPanel";
import { KnowledgeBaseLoadStatus } from "./KnowledgeBaseLoadStatus";
import { KnowledgeBaseMetricsHeader } from "./KnowledgeBaseMetricsHeader";
import { KnowledgeBaseSearchPanel } from "./KnowledgeBaseSearchPanel";
import { KnowledgeBaseSettingsDialog } from "./KnowledgeBaseSettingsDialog";

export function KnowledgeBaseDetailPage() {
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

  const [showSettings, setShowSettings] = useState(false);
  // Kept so a duplicate-rejected upload can retry with replace=true.
  const [lastFile, setLastFile] = useState<File | null>(null);

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

  // The resource-level view of the KB (description + config) backing the
  // settings dialog; metrics alone don't carry the config.
  const kbQuery = useQuery({
    queryKey: ["kb-resource", name],
    queryFn: () => getKnowledgeBase(name),
    enabled: Boolean(name),
  });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["kb-documents", name] });
    void qc.invalidateQueries({ queryKey: ["kb-metrics", name] });
  };

  const ingest = useMutation({
    mutationFn: (input: { file: File; replace: boolean }) =>
      ingestDocument(name, input.file, input.replace),
    onSuccess: () => {
      setLastFile(null);
      invalidate();
    },
  });

  const updateConfig = useMutation({
    mutationFn: (config: KnowledgeBaseConfigOut) => updateKnowledgeBaseConfig(name, config),
    onSuccess: () => {
      setShowSettings(false);
      void qc.invalidateQueries({ queryKey: ["kb-resource", name] });
      invalidate();
    },
  });

  const reconvert = useMutation({
    mutationFn: (id: string) => reconvertDocument(name, id),
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
    if (f) {
      setLastFile(f);
      ingest.mutate({ file: f, replace: false });
    }
    e.target.value = "";
  };

  // A duplicate-rejected upload retries with replace=true while we hold the file.
  const canRetryWithReplace =
    lastFile !== null &&
    ingest.error instanceof ApiError &&
    ingest.error.code === "INGEST_REJECTED";

  // Surface list/metrics query failures instead of rendering blank sections.
  const loadError = docsQuery.error ?? metricsQuery.error;

  return (
    <div className="space-y-6 p-6">
      <KnowledgeBaseMetricsHeader
        name={name}
        metrics={metricsQuery.data}
        reindexResult={reindex.data}
        isReindexPending={reindex.isPending}
        onReindex={() => reindex.mutate()}
        canOpenSettings={Boolean(kbQuery.data)}
        onOpenSettings={() => setShowSettings(true)}
      />

      {showSettings && kbQuery.data ? (
        // Mounted fresh on each open so the form re-seeds from the latest config.
        <KnowledgeBaseSettingsDialog
          open
          onOpenChange={(o) => {
            if (!o) updateConfig.reset();
            setShowSettings(o);
          }}
          config={kbQuery.data.config}
          error={updateConfig.error}
          isPending={updateConfig.isPending}
          onSubmit={(config) => updateConfig.mutate(config)}
        />
      ) : null}

      <KnowledgeBaseLoadStatus
        error={loadError}
        isLoading={docsQuery.isPending || metricsQuery.isPending}
      />

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
        reconvertError={reconvert.error}
        isReconvertPending={reconvert.isPending}
        onRetryWithReplace={
          canRetryWithReplace && lastFile
            ? () => ingest.mutate({ file: lastFile, replace: true })
            : null
        }
        onReconvert={(id) => reconvert.mutate(id)}
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
