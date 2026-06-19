// frontend/src/pages/KnowledgePage.tsx
// The unified 知识 surface (specs 006 FR-019 + 007 FR-017b, ADR-030): ONE entry
// replacing the split Memory + Knowledge-base pages. Primary axis = scope
// (全局 + projects); within a scope a store's notes and that scope's documents
// are listed together (each type-tagged), with an add-by-shape input and a
// trash. Viewers stay READ-ONLY (no in-app editor). Selected scope + item are
// route/UI state; data + mutations live in useKnowledge.
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Button } from "@/components/ui/button";
import { KnowledgeScopeNav } from "@/components/knowledge/KnowledgeScopeNav";
import { KnowledgeAddBar } from "@/components/knowledge/KnowledgeAddBar";
import { KnowledgeList } from "@/components/knowledge/KnowledgeList";
import { KnowledgeItemViewer } from "@/components/knowledge/KnowledgeItemViewer";
import { KnowledgeTrashPanel } from "@/components/knowledge/KnowledgeTrashPanel";
import { translateApiError } from "@/lib/api/errors";
import {
  useKnowledgeBases,
  useKnowledgeItems,
  useKnowledgeMutations,
  useKnowledgeScopes,
  useKnowledgeTrash,
} from "@/lib/hooks/useKnowledge";
import { Library } from "lucide-react";
import type { KnowledgeItem, KnowledgeScope } from "@/lib/api/knowledge";

export function KnowledgePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const scopeId = useParams<{ scopeId: string }>().scopeId;

  const scopesQuery = useKnowledgeScopes();
  const kbsQuery = useKnowledgeBases();
  const scopes = scopesQuery.data ?? [];
  const kbs = kbsQuery.data ?? [];

  // The active scope: the route param, else the first scope (global). Selecting
  // a scope is navigation, so it survives reload / deep-link (frontend.md §3).
  const scope: KnowledgeScope | undefined = scopes.find((s) => s.id === scopeId) ?? scopes[0];

  const itemsQuery = useKnowledgeItems(scope, kbs);
  const trashQuery = useKnowledgeTrash(scope, kbs);
  const m = useKnowledgeMutations(scope?.id);

  const [selected, setSelected] = useState<KnowledgeItem | null>(null);
  const [showTrash, setShowTrash] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<KnowledgeItem | null>(null);

  // The selected item kept in sync with the freshly-loaded list (it disappears
  // once deleted; its lock/title refresh after a mutation).
  const liveSelected = selected
    ? (itemsQuery.data?.find((i) => i.ref === selected.ref) ?? null)
    : null;

  const onAddNote = (text: string) => {
    if (scope?.memoryStoreName) m.addNote.mutate({ store: scope.memoryStoreName, input: { text } });
  };
  const onUploadFile = (kb: string, file: File) => {
    if (scope) m.uploadDocument.mutate({ kb, file, projectId: scope.id });
  };

  const confirmDelete = (item: KnowledgeItem) => setPendingDelete(item);
  const performDelete = () => {
    const item = pendingDelete;
    if (!item) return;
    const done = () => {
      setPendingDelete(null);
      setSelected(null);
    };
    if (item.type === "note" && item.storeName && item.factId) {
      m.removeNote.mutate({ store: item.storeName, factId: item.factId }, { onSuccess: done });
    } else if (item.type === "document" && item.kbName && item.documentId) {
      m.deleteOrPurgeDocument.mutate(
        { kb: item.kbName, documentId: item.documentId },
        { onSuccess: done },
      );
    }
  };

  const onRestore = (item: KnowledgeItem) => {
    if (item.kbName && item.documentId)
      m.restore.mutate({ kb: item.kbName, documentId: item.documentId });
  };
  const onPurge = (item: KnowledgeItem) => {
    // Deleting an already-trashed document purges it (FR-023).
    if (item.kbName && item.documentId)
      m.deleteOrPurgeDocument.mutate({ kb: item.kbName, documentId: item.documentId });
  };

  const loadError = scopesQuery.error ?? kbsQuery.error ?? itemsQuery.error;
  const trashBusy = m.restore.isPending || m.deleteOrPurgeDocument.isPending;
  const deleteBusy = m.removeNote.isPending || m.deleteOrPurgeDocument.isPending;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Library}
        title={t("knowledge.title")}
        subtitle={t("knowledge.subtitle")}
        actions={
          <Button variant="outline" onClick={() => setShowTrash(true)}>
            {t("knowledge.trash.open")}
          </Button>
        }
      />

      {loadError ? (
        <Card>
          <CardContent className="py-4 text-sm text-destructive" role="alert">
            {translateApiError(t, loadError)}
          </CardContent>
        </Card>
      ) : null}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-[minmax(180px,240px)_1fr]">
        <KnowledgeScopeNav
          scopes={scopes}
          selectedId={scope?.id}
          onSelect={(s) => {
            setSelected(null);
            navigate(`/knowledge/${s.id}`);
          }}
        />

        <div className="min-w-0 space-y-4">
          <KnowledgeAddBar
            kbs={kbs}
            canAddNote={Boolean(scope?.memoryStoreName)}
            isAddingNote={m.addNote.isPending}
            isUploading={m.uploadDocument.isPending}
            onAddNote={onAddNote}
            onUploadFile={onUploadFile}
          />

          {m.uploadDocument.error ? (
            <p className="text-sm text-destructive" role="alert">
              {translateApiError(t, m.uploadDocument.error)}
            </p>
          ) : null}

          {liveSelected ? (
            <KnowledgeItemViewer
              item={liveSelected}
              isDeletePending={deleteBusy}
              onDelete={() => confirmDelete(liveSelected)}
              onClose={() => setSelected(null)}
            />
          ) : null}

          {itemsQuery.isPending ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                {t("common.loading")}
              </CardContent>
            </Card>
          ) : (
            <KnowledgeList items={itemsQuery.data ?? []} onSelect={setSelected} />
          )}
        </div>
      </div>

      <KnowledgeTrashPanel
        open={showTrash}
        onOpenChange={setShowTrash}
        items={trashQuery.data ?? []}
        isLoading={trashQuery.isPending}
        isBusy={trashBusy}
        onRestore={onRestore}
        onPurge={onPurge}
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title={t(
          pendingDelete?.type === "document"
            ? "knowledge.deleteDocConfirm"
            : "knowledge.deleteNoteConfirm",
          { title: pendingDelete?.title ?? "" },
        )}
        confirmLabel={deleteBusy ? t("common.deleting") : t("common.delete")}
        pending={deleteBusy}
        onConfirm={performDelete}
      />
    </div>
  );
}
