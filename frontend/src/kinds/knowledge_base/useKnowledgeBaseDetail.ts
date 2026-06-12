// frontend/src/kinds/knowledge_base/useKnowledgeBaseDetail.ts
//
// All data + mutations for the KB detail surface, extracted so the page stays a
// thin view (under the size ceiling). Owns the four queries (documents /
// metrics / resource / selected-document), the seven write mutations, and the
// derived helpers (run search by mode, select a doc, confirm-then-delete,
// upload + duplicate-replace retry).
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
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

export function useKnowledgeBaseDetail(name: string) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<RetrievalMode>("keyword");
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [grepResult, setGrepResult] = useState<GrepResponse | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");

  const [showSettings, setShowSettings] = useState(false);
  const [lastFile, setLastFile] = useState<File | null>(null);

  const docsQuery = useQuery({
    queryKey: ["kb-documents", name],
    queryFn: () => listDocuments(name, 100, 0),
    enabled: Boolean(name),
  });
  const metricsQuery = useQuery({
    queryKey: ["kb-metrics", name],
    queryFn: () => getKnowledgeBaseMetrics(name),
    enabled: Boolean(name),
  });
  const kbQuery = useQuery({
    queryKey: ["kb-resource", name],
    queryFn: () => getKnowledgeBase(name),
    enabled: Boolean(name),
  });
  const docDetailQuery = useQuery({
    queryKey: ["kb-document", name, selectedId],
    queryFn: () => getDocument(name, selectedId as string),
    enabled: Boolean(name && selectedId),
  });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["kb-documents", name] });
    void qc.invalidateQueries({ queryKey: ["kb-metrics", name] });
  };
  const invalidateSelected = () => {
    if (selectedId) void qc.invalidateQueries({ queryKey: ["kb-document", name, selectedId] });
  };

  const ingest = useMutation({
    mutationFn: (input: { file: File; replace: boolean }) =>
      ingestDocument(name, input.file, input.replace),
    onSuccess: (doc) => {
      setLastFile(null);
      setSelectedId(doc.id);
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
    onSuccess: () => {
      invalidate();
      invalidateSelected();
    },
  });
  const del = useMutation({
    mutationFn: (id: string) => deleteDocument(name, id),
    onSuccess: () => {
      setSelectedId(null);
      setEditing(false);
      invalidate();
    },
  });
  const edit = useMutation({
    mutationFn: (input: { id: string; markdown: string }) =>
      editDocument(name, input.id, input.markdown),
    onSuccess: () => {
      setEditing(false);
      setEditText("");
      invalidate();
      invalidateSelected();
    },
  });
  const reindex = useMutation({
    mutationFn: () => reindexKnowledgeBase(name),
    onSuccess: invalidate,
  });
  const search = useMutation({
    mutationFn: () => searchKnowledgeBase(name, query, { topK: 5, mode }),
    onSuccess: (data) => {
      setGrepResult(null);
      setSearchResult(data);
    },
  });
  const grep = useMutation({
    mutationFn: () => grepKnowledgeBase(name, query, 100),
    onSuccess: (data) => {
      setSearchResult(null);
      setGrepResult(data);
    },
  });

  const runSearch = () => (mode === "grep" ? grep.mutate() : search.mutate());
  const selectDoc = (id: string) => {
    setSelectedId(id);
    setEditing(false);
  };
  const confirmDelete = () => {
    if (!selectedId) return;
    const title = docDetailQuery.data?.title ?? selectedId;
    if (window.confirm(t("knowledgeBases.detail.deleteConfirm", { title }))) del.mutate(selectedId);
  };
  const startEdit = () => {
    setEditText(docDetailQuery.data?.markdown ?? "");
    setEditing(true);
  };
  const cancelEdit = () => {
    setEditing(false);
    setEditText("");
  };
  const saveEdit = () => {
    if (selectedId) edit.mutate({ id: selectedId, markdown: editText });
  };

  const handlePickFile = () => fileInputRef.current?.click();
  const handleFileChange: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const f = e.target.files?.[0];
    if (f) {
      setLastFile(f);
      ingest.mutate({ file: f, replace: false });
    }
    e.target.value = "";
  };
  const retryReplace = () => {
    if (lastFile) ingest.mutate({ file: lastFile, replace: true });
  };

  const canRetryWithReplace =
    lastFile !== null &&
    ingest.error instanceof ApiError &&
    ingest.error.code === "INGEST_REJECTED";

  return {
    fileInputRef,
    query,
    setQuery,
    mode,
    setMode,
    searchResult,
    grepResult,
    selectedId,
    editing,
    editText,
    setEditText,
    showSettings,
    setShowSettings,
    docsQuery,
    metricsQuery,
    kbQuery,
    docDetailQuery,
    ingest,
    updateConfig,
    reconvert,
    del,
    edit,
    reindex,
    search,
    grep,
    runSearch,
    selectDoc,
    confirmDelete,
    startEdit,
    cancelEdit,
    saveEdit,
    handlePickFile,
    handleFileChange,
    retryReplace,
    canRetryWithReplace,
    loadError: docsQuery.error ?? metricsQuery.error,
  };
}
