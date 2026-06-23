// frontend/src/kinds/knowledge_base/useKnowledgeBaseDetail.ts
//
// All data + mutations for the KB detail surface, extracted so the page stays a
// thin view. The document list is fetched in ONE request (up to the API max) and
// rendered as a single scrollable list — no in-UI pager (the documents API still
// supports `limit`/`offset` for programmatic callers).
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";
import {
  checkSources,
  deleteDocument,
  getDocument,
  getKnowledgeBase,
  getKnowledgeBaseMetrics,
  ingestDocument,
  listDocuments,
  reconvertDocument,
  reembedDocuments,
  reindexKnowledgeBase,
  searchKnowledgeBase,
  updateFromSource,
  updateKnowledgeBaseConfig,
  type DocumentListOut,
  type KnowledgeBaseConfigOut,
  type ReembedBatchRequest,
  type SearchResponse,
  type SourceCheckResponse,
} from "./api";

/** Poll the document list while any document is still embedding/queued/running so
 * the per-document status badge updates live; stop once everything settles. */
const _BUSY = new Set(["embedding", "queued", "running"]);
function embedInFlight(data: DocumentListOut | undefined): number | false {
  return (data?.documents ?? []).some((d) => _BUSY.has(d.embed_status ?? "")) ? 2000 : false;
}

// The document list is shown as a single scrollable list, fetched in one request
// at the documents API's max page size (`le=200`) — enough for a personal KB.
const DOCS_FETCH_LIMIT = 200;

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

  const docsQuery = useQuery({
    queryKey: ["kb-documents", name],
    queryFn: () => listDocuments(name, DOCS_FETCH_LIMIT, 0),
    enabled: Boolean(name),
    // Live-refresh the per-document embed status while a re-embed is in flight.
    refetchInterval: (query) => embedInFlight(query.state.data),
  });
  const docTotal = docsQuery.data?.total ?? 0;
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
      setSearchResult(null); // a delete returns to the full list (no stale hit rows)
      invalidate();
    },
  });
  const reindex = useMutation({
    mutationFn: () => reindexKnowledgeBase(name),
    onSuccess: invalidate,
  });
  // Enqueue async re-embed (off the request path); the list poll reflects each
  // document flipping embedding → done as the worker drains.
  const reembed = useMutation({
    mutationFn: (body: ReembedBatchRequest) => reembedDocuments(name, body),
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

  // Recall mode: a search filters the tree to the deduped hit docs (passages carry
  // the title) and opens the top hit highlighted; clearing the box restores the list.
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
    docTotal,
    metricsQuery,
    kbQuery,
    docDetailQuery,
    ingest,
    updateConfig,
    reconvert,
    del,
    reindex,
    reembed,
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
