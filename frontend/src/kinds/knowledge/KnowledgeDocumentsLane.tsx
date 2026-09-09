// frontend/src/kinds/knowledge/KnowledgeDocumentsLane.tsx
//
// Documents lane of a knowledge scope: files someone ingested (any format,
// converted to Markdown server-side) under `<scope>/inbox/`. ONE retrieval bar
// (one query → one answer; the backend auto-selects the strategy), the document
// tree on the left and a read-only preview on the right — the same shape as the
// Entries lane next door, over a different lane of the same scope. A duplicate
// upload can be retried with replace=true. State + mutations live in
// useKnowledgeDocuments, which the page owns (the header's Upload / Reindex /
// Check sources actions drive the same state).
import { useTranslation } from "react-i18next";

import { ApiError } from "@/lib/api/errors";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { KnowledgeDocTree } from "./KnowledgeDocTree";
import { KnowledgeDocViewer } from "./KnowledgeDocViewer";
import { KnowledgeLoadStatus } from "./KnowledgeLoadStatus";
import { KnowledgeSearchBar } from "./KnowledgeSearchBar";
import type { KnowledgeDocumentsState } from "./useKnowledgeDocuments";

export function KnowledgeDocumentsLane({ docs }: { docs: KnowledgeDocumentsState }) {
  const { t } = useTranslation();

  // In recall mode the tree IS the deduped hit set; otherwise it's the fetched
  // documents. Both reduce to plain {id, title, sourceMode, embedStatus} rows.
  const treeItems = docs.recalling
    ? docs.recallDocs
    : (docs.docsQuery.data?.documents ?? []).map((d) => ({
        id: d.id,
        title: d.title,
        sourceMode: d.source_mode,
        embedStatus: d.embed_status,
      }));

  return (
    <div className="space-y-3">
      <KnowledgeLoadStatus
        error={docs.loadError}
        isLoading={docs.docsQuery.isPending || docs.metricsQuery.isPending}
      />

      {docs.ingest.error ? (
        <p className="text-sm text-destructive" role="alert">
          {docs.ingest.error instanceof ApiError
            ? docs.ingest.error.message
            : String(docs.ingest.error)}
          {docs.canRetryWithReplace ? (
            <button type="button" className="ml-2 underline" onClick={docs.retryReplace}>
              {t("knowledge.detail.replaceExisting")}
            </button>
          ) : null}
        </p>
      ) : null}

      <KnowledgeSearchBar
        query={docs.query}
        error={docs.search.error}
        isPending={docs.search.isPending}
        onQueryChange={docs.onQueryChange}
        onSearch={docs.runSearch}
        placeholder={t("knowledge.detail.searchPlaceholder")}
        actionLabel={t("knowledge.detail.search")}
      />

      <p className="px-1 text-xs text-muted-foreground">{t("knowledge.lanes.intro.documents")}</p>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(220px,300px)_1fr]">
        <KnowledgeDocTree
          items={treeItems}
          selectedId={docs.selectedId}
          isLoading={docs.recalling ? false : docs.docsQuery.isPending}
          total={docs.recalling ? treeItems.length : docs.docTotal}
          onSelect={docs.selectDoc}
          emptyLabel={docs.recalling ? t("knowledge.detail.noMatches") : undefined}
        />
        <KnowledgeDocViewer
          doc={docs.docDetailQuery.data}
          initialQuery={docs.recalling ? docs.query : ""}
          isLoading={Boolean(docs.selectedId) && docs.docDetailQuery.isPending}
          isReconvertPending={docs.reconvert.isPending}
          isDeletePending={docs.del.isPending}
          reconvertError={docs.reconvert.error}
          onReconvert={() => docs.selectedId && docs.reconvert.mutate(docs.selectedId)}
          onDelete={docs.confirmDelete}
        />
      </div>

      <ConfirmDialog
        open={docs.deleteOpen}
        onOpenChange={docs.setDeleteOpen}
        title={t("knowledge.detail.deleteDocConfirm", { title: docs.deleteTitle })}
        confirmLabel={docs.del.isPending ? t("common.deleting") : t("common.delete")}
        pending={docs.del.isPending}
        onConfirm={docs.performDelete}
      />
    </div>
  );
}
