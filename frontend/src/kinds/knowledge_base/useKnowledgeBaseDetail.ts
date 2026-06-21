// frontend/src/kinds/knowledge_base/useKnowledgeBaseDetail.ts
//
// All data + mutations for the KB detail surface, extracted so the page stays a
// thin view. Documents are page-paginated (server offset) with a debounced
// server-side title filter (`q`).
import { useEffect, useRef, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";
import { usePagedList, usePageClamp } from "@/lib/hooks/usePagedList";
import {
  checkSources,
  deleteDocument,
  getDocument,
  getKnowledgeBase,
  getKnowledgeBaseMetrics,
  ingestDocument,
  listDocuments,
  reconvertDocument,
  reindexKnowledgeBase,
  searchKnowledgeBase,
  updateFromSource,
  updateKnowledgeBaseConfig,
  type KnowledgeBaseConfigOut,
  type SearchResponse,
  type SourceCheckResponse,
} from "./api";

// Default page size for the document tree's page-based pagination.
const DEFAULT_DOCS_PAGE_SIZE = 50;

export function useKnowledgeBaseDetail(name: string) {
  const qc = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState("");
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [showSettings, setShowSettings] = useState(false);
  const [lastFile, setLastFile] = useState<File | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);

  // The latest source-check report; non-null opens the report dialog.
  const [sourceReport, setSourceReport] = useState<SourceCheckResponse | null>(null);

  // Page-based pagination (server offset).
  const {
    page: docPage,
    setPage: setDocPage,
    pageSize: docPageSize,
    setPageSize: setDocPageSize,
    offset: docOffset,
  } = usePagedList(DEFAULT_DOCS_PAGE_SIZE);

  const docsQuery = useQuery({
    queryKey: ["kb-documents", name, docPage, docPageSize],
    queryFn: () => listDocuments(name, docPageSize, docOffset),
    enabled: Boolean(name),
    // Keep the prior page's rows + total while the next page loads, so the page
    // count doesn't transiently read as 1 and trip the clamp during a forward nav.
    placeholderData: keepPreviousData,
  });
  const docTotal = docsQuery.data?.total ?? 0;
  const docPageCount = Math.max(1, Math.ceil(docTotal / docPageSize));
  // Pull the page back into range when the total shrinks (last page emptied).
  usePageClamp(docPage, docPageCount, setDocPage);
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
      invalidate();
    },
  });
  const reindex = useMutation({
    mutationFn: () => reindexKnowledgeBase(name),
    onSuccess: invalidate,
  });
  const checkSourcesM = useMutation({
    mutationFn: () => checkSources(name),
    onSuccess: (report) => {
      // An "updated" entry means a doc was auto-re-ingested in place — refresh
      // the lists/metrics so the new chunk counts show.
      if (report.sources.some((s) => s.status === "updated")) {
        invalidate();
        invalidateSelected();
      }
      setSourceReport(report);
    },
  });
  const updateFromSourceM = useMutation({
    mutationFn: (id: string) => updateFromSource(name, id),
    onSuccess: () => {
      invalidate();
      invalidateSelected();
      // Re-run the scan so the just-updated row flips out of "changed".
      checkSourcesM.mutate();
    },
  });
  const search = useMutation({
    mutationFn: () => searchKnowledgeBase(name, query, { topK: 5 }),
    onSuccess: (data) => {
      setSearchResult(data);
    },
  });

  // Recall mode: a search filters the tree to the deduped hit docs and opens the
  // top hit highlighted; clearing the box returns to the full paged list. Passages
  // carry the title, so hit rows render without an extra fetch.
  const recalling = searchResult !== null;
  const recallDocs: { id: string; title: string }[] = [];
  const seenHits = new Set<string>();
  for (const p of searchResult?.passages ?? []) {
    if (seenHits.has(p.document_id)) continue;
    seenHits.add(p.document_id);
    recallDocs.push({ id: p.document_id, title: p.title });
  }
  useEffect(() => {
    // Auto-select the top hit so its match opens highlighted in the viewer.
    if (searchResult?.passages.length) setSelectedId(searchResult.passages[0].document_id);
  }, [searchResult]);
  const onQueryChange = (value: string) => {
    setQuery(value);
    if (!value) setSearchResult(null); // clearing the box exits recall mode
  };

  const runSearch = () => search.mutate();
  const selectDoc = (id: string) => setSelectedId(id);
  // Open the styled confirmation dialog (no native window.confirm). The page
  // renders <ConfirmDialog open={deleteOpen} .../> and calls performDelete.
  const confirmDelete = () => {
    if (selectedId) setDeleteOpen(true);
  };
  const performDelete = () => {
    if (selectedId) del.mutate(selectedId, { onSuccess: () => setDeleteOpen(false) });
  };
  const deleteTitle = docDetailQuery.data?.title ?? selectedId ?? "";

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
    searchResult,
    selectedId,
    showSettings,
    setShowSettings,
    docsQuery,
    docPage,
    setDocPage,
    docPageSize,
    setDocPageSize,
    docTotal,
    docPageCount,
    metricsQuery,
    kbQuery,
    docDetailQuery,
    ingest,
    updateConfig,
    reconvert,
    del,
    reindex,
    checkSources: checkSourcesM,
    updateFromSource: updateFromSourceM,
    sourceReport,
    setSourceReport,
    search,
    runSearch,
    selectDoc,
    recalling,
    recallDocs,
    onQueryChange,
    confirmDelete,
    performDelete,
    deleteOpen,
    setDeleteOpen,
    deleteTitle,
    handlePickFile,
    handleFileChange,
    retryReplace,
    canRetryWithReplace,
    loadError: docsQuery.error ?? metricsQuery.error,
  };
}
