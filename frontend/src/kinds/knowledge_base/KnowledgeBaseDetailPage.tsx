// frontend/src/kinds/knowledge_base/KnowledgeBaseDetailPage.tsx
//
// KB detail surface (spec 006 redesign): a back link + header (metrics +
// Settings/Reindex/Upload), ONE unified retrieval bar (keyword/vector/grep),
// and a document tree on the left with a preview/editor on the right. Uploads
// accept any format (converted to Markdown server-side); a duplicate upload can
// be retried with replace=true. The KB is agent-read-only; all writes are
// user-curated. State + mutations live in useKnowledgeBaseDetail.
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/lib/api/errors";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { KnowledgeBaseDetailHeader } from "./KnowledgeBaseDetailHeader";
import { KnowledgeBaseDocTree } from "./KnowledgeBaseDocTree";
import { KnowledgeBaseDocViewer } from "./KnowledgeBaseDocViewer";
import { KnowledgeBaseLoadStatus } from "./KnowledgeBaseLoadStatus";
import { KnowledgeBaseSearchBar } from "./KnowledgeBaseSearchBar";
import { KnowledgeBaseSettingsDialog } from "./KnowledgeBaseSettingsDialog";
import { useKnowledgeBaseDetail } from "./useKnowledgeBaseDetail";

export function KnowledgeBaseDetailPage() {
  const { t } = useTranslation();
  const name = useParams<{ name: string }>().name ?? "";
  const kb = useKnowledgeBaseDetail(name);

  return (
    <div className="space-y-6 p-6">
      <KnowledgeBaseDetailHeader
        name={name}
        metrics={kb.metricsQuery.data}
        isReindexPending={kb.reindex.isPending}
        isUploadPending={kb.ingest.isPending}
        canOpenSettings={Boolean(kb.kbQuery.data)}
        onReindex={() => kb.reindex.mutate()}
        onOpenSettings={() => kb.setShowSettings(true)}
        onUpload={kb.handlePickFile}
      />

      {kb.showSettings && kb.kbQuery.data ? (
        <KnowledgeBaseSettingsDialog
          open
          onOpenChange={(o) => {
            if (!o) kb.updateConfig.reset();
            kb.setShowSettings(o);
          }}
          config={kb.kbQuery.data.config}
          error={kb.updateConfig.error}
          isPending={kb.updateConfig.isPending}
          onSubmit={(config) => kb.updateConfig.mutate(config)}
        />
      ) : null}

      <KnowledgeBaseLoadStatus
        error={kb.loadError}
        isLoading={kb.docsQuery.isPending || kb.metricsQuery.isPending}
      />

      {kb.ingest.error ? (
        <p className="text-sm text-destructive" role="alert">
          {kb.ingest.error instanceof ApiError ? kb.ingest.error.message : String(kb.ingest.error)}
          {kb.canRetryWithReplace ? (
            <button type="button" className="ml-2 underline" onClick={kb.retryReplace}>
              {t("knowledgeBases.detail.replaceExisting")}
            </button>
          ) : null}
        </p>
      ) : null}

      <KnowledgeBaseSearchBar
        query={kb.query}
        mode={kb.mode}
        searchResult={kb.searchResult}
        grepResult={kb.grepResult}
        error={kb.search.error ?? kb.grep.error}
        isPending={kb.search.isPending || kb.grep.isPending}
        onQueryChange={kb.setQuery}
        onModeChange={kb.setMode}
        onSearch={kb.runSearch}
        onSelectDocument={kb.selectDoc}
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(220px,300px)_1fr]">
        <KnowledgeBaseDocTree
          docs={kb.docsQuery.data}
          selectedId={kb.selectedId}
          isLoading={kb.docsQuery.isPending}
          isLoadingMore={kb.docsQuery.isFetching}
          onLoadMore={kb.loadMoreDocuments}
          onSelect={kb.selectDoc}
        />
        <KnowledgeBaseDocViewer
          doc={kb.docDetailQuery.data}
          isLoading={Boolean(kb.selectedId) && kb.docDetailQuery.isPending}
          isReconvertPending={kb.reconvert.isPending}
          isDeletePending={kb.del.isPending}
          isLockPending={kb.setLock.isPending}
          reconvertError={kb.reconvert.error}
          onReconvert={() => kb.selectedId && kb.reconvert.mutate(kb.selectedId)}
          onDelete={kb.confirmDelete}
          onToggleLock={() =>
            kb.docDetailQuery.data &&
            kb.setLock.mutate({
              id: kb.docDetailQuery.data.id,
              locked: !kb.docDetailQuery.data.locked,
            })
          }
        />
      </div>

      <input ref={kb.fileInputRef} type="file" className="hidden" onChange={kb.handleFileChange} />

      <ConfirmDialog
        open={kb.deleteOpen}
        onOpenChange={kb.setDeleteOpen}
        title={t("knowledgeBases.detail.deleteConfirm", { title: kb.deleteTitle })}
        confirmLabel={kb.del.isPending ? t("common.deleting") : t("common.delete")}
        pending={kb.del.isPending}
        onConfirm={kb.performDelete}
      />
    </div>
  );
}
