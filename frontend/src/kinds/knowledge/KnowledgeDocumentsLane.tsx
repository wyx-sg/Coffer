// frontend/src/kinds/knowledge/KnowledgeDocumentsLane.tsx
//
// Documents lane of a knowledge scope: files someone uploaded (any format,
// converted to Markdown server-side) under `<scope>/docs/`. A CLIENT-SIDE
// filter box on top (matches filenames as you type — no request, no button),
// the document tree on the left and a read-only preview on the right — the
// same shape as the Notes lane next door, over a different lane of the same
// scope. A duplicate upload can be retried with replace=true. State +
// mutations live in useKnowledgeDocuments, which the page owns (the header's
// Upload / Tidy / overflow actions drive the same state).
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/lib/api/errors";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { SearchInput } from "@/components/SearchInput";
import { KnowledgeDocTree } from "./KnowledgeDocTree";
import { KnowledgeDocViewer } from "./KnowledgeDocViewer";
import { KnowledgeLoadStatus } from "./KnowledgeLoadStatus";
import { matchesFilter } from "./filter";
import type { KnowledgeDocumentsState } from "./useKnowledgeDocuments";

export function KnowledgeDocumentsLane({ docs }: { docs: KnowledgeDocumentsState }) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("");

  const treeItems = (docs.docsQuery.data?.documents ?? [])
    .filter((d) => matchesFilter(filter, d.title, d.path))
    .map((d) => ({
      id: d.id,
      title: d.title,
      sourceMode: d.source_mode,
      embedStatus: d.embed_status,
    }));
  const filtering = filter.trim().length > 0;

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

      <SearchInput
        className="min-w-[16rem] max-w-sm"
        value={filter}
        onChange={setFilter}
        placeholder={t("knowledge.detail.filterPlaceholder")}
        ariaLabel={t("knowledge.detail.filterPlaceholder")}
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(220px,300px)_1fr]">
        <KnowledgeDocTree
          items={treeItems}
          selectedId={docs.selectedId}
          isLoading={docs.docsQuery.isPending}
          total={treeItems.length}
          onSelect={docs.selectDoc}
          emptyLabel={filtering ? t("knowledge.detail.noMatches") : undefined}
        />
        <KnowledgeDocViewer
          doc={docs.docDetailQuery.data}
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
