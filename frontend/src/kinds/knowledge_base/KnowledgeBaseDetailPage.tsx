// frontend/src/kinds/knowledge_base/KnowledgeBaseDetailPage.tsx
//
// KB detail surface (spec 006 redesign): a back link + header (metrics +
// Settings/Reindex/Upload), ONE retrieval bar (one query → one answer; the
// backend auto-selects the strategy), and a document tree on the left (paged,
// server-side title filter) with a preview/editor on the right. Uploads
// accept any format (converted to Markdown server-side); a duplicate upload can
// be retried with replace=true. The KB is agent-read-only; all writes are
// user-curated. State + mutations live in useKnowledgeBaseDetail.
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ApiError, translateApiError } from "@/lib/api/errors";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { KnowledgeBaseDetailHeader } from "./KnowledgeBaseDetailHeader";
import { KnowledgeBaseDocTree } from "./KnowledgeBaseDocTree";
import { KnowledgeBaseDocViewer } from "./KnowledgeBaseDocViewer";
import { KnowledgeBaseLoadStatus } from "./KnowledgeBaseLoadStatus";
import { KnowledgeBaseSearchBar } from "./KnowledgeBaseSearchBar";
import { KnowledgeBaseSettingsDialog } from "./KnowledgeBaseSettingsDialog";
import { SourceCheckDialog } from "./SourceCheckDialog";
import { useKnowledgeBaseDetail } from "./useKnowledgeBaseDetail";

export function KnowledgeBaseDetailPage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const name = useParams<{ name: string }>().name ?? "";
  const kb = useKnowledgeBaseDetail(name);

  const onCheckSources = () =>
    kb.checkSources.mutate(undefined, {
      onError: (e) => toast.error(translateApiError(t, e)),
    });
  const onUpdateFromSource = (id: string) =>
    kb.updateFromSource.mutate(id, {
      onSuccess: () => toast.success(t("knowledgeBases.detail.sourceCheck.updated")),
      // The edited-refusal (and any other failure) surfaces as a toast.
      onError: (e) => toast.error(translateApiError(t, e)),
    });

  // In recall mode the tree IS the deduped hit set; otherwise it's the current
  // paged documents. Both reduce to plain {id, title, sourceMode} rows.
  const treeItems = kb.recalling
    ? kb.recallDocs
    : (kb.docsQuery.data?.documents ?? []).map((d) => ({
        id: d.id,
        title: d.title,
        sourceMode: d.source_mode,
        embedStatus: d.embed_status,
      }));

  return (
    <div className="space-y-6 p-6">
      <KnowledgeBaseDetailHeader
        name={name}
        metrics={kb.metricsQuery.data}
        isReindexPending={kb.reindex.isPending}
        isUploadPending={kb.ingest.isPending}
        checkingSources={kb.checkSources.isPending}
        canOpenSettings={Boolean(kb.kbQuery.data)}
        onReindex={() => kb.reindex.mutate()}
        onCheckSources={onCheckSources}
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

      {kb.sourceReport ? (
        <SourceCheckDialog
          open
          onOpenChange={(o) => {
            if (!o) kb.setSourceReport(null);
          }}
          report={kb.sourceReport}
          updatingId={kb.updateFromSource.isPending ? kb.updateFromSource.variables : null}
          onUpdate={onUpdateFromSource}
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
        error={kb.search.error}
        isPending={kb.search.isPending}
        onQueryChange={kb.onQueryChange}
        onSearch={kb.runSearch}
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(220px,300px)_1fr]">
        <KnowledgeBaseDocTree
          items={treeItems}
          selectedId={kb.selectedId}
          isLoading={kb.recalling ? false : kb.docsQuery.isPending}
          total={kb.recalling ? treeItems.length : kb.docTotal}
          onSelect={kb.selectDoc}
          emptyLabel={kb.recalling ? t("knowledgeBases.detail.noMatches") : undefined}
        />
        <KnowledgeBaseDocViewer
          doc={kb.docDetailQuery.data}
          initialQuery={kb.recalling ? kb.query : ""}
          isLoading={Boolean(kb.selectedId) && kb.docDetailQuery.isPending}
          isReconvertPending={kb.reconvert.isPending}
          isDeletePending={kb.del.isPending}
          reconvertError={kb.reconvert.error}
          onReconvert={() => kb.selectedId && kb.reconvert.mutate(kb.selectedId)}
          onDelete={kb.confirmDelete}
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
