// frontend/src/kinds/knowledge_base/KnowledgeBaseDocumentList.tsx
//
// Documents section: the Upload action (any format → Markdown on the server)
// and the document list with per-doc Markdown edit (inline textarea), a
// source_mode badge, reconvert (converted docs only), and delete. All state,
// mutations, and the hidden file input live in the page; this component is
// presentational.
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import { type DocumentListOut, type DocumentOut } from "./api";

interface Props {
  docs: DocumentListOut | undefined;
  ingestError: unknown;
  isIngestPending: boolean;
  reconvertError: unknown;
  isReconvertPending: boolean;
  editingId: string | null;
  editText: string;
  isStartEditPending: boolean;
  isDeletePending: boolean;
  isEditPending: boolean;
  onPickFile: () => void;
  /** Non-null after a duplicate-rejected upload: retries it with replace=true. */
  onRetryWithReplace: (() => void) | null;
  onReconvert: (id: string) => void;
  onStartEdit: (id: string) => void;
  onDelete: (id: string) => void;
  onEditTextChange: (value: string) => void;
  onSaveEdit: (id: string) => void;
  onCancelEdit: () => void;
}

export function KnowledgeBaseDocumentList({
  docs,
  ingestError,
  isIngestPending,
  reconvertError,
  isReconvertPending,
  editingId,
  editText,
  isStartEditPending,
  isDeletePending,
  isEditPending,
  onPickFile,
  onRetryWithReplace,
  onReconvert,
  onStartEdit,
  onDelete,
  onEditTextChange,
  onSaveEdit,
  onCancelEdit,
}: Props) {
  const { t } = useTranslation();
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">{t("knowledgeBases.detail.documents")}</h2>
        <Button onClick={onPickFile} disabled={isIngestPending}>
          {isIngestPending ? t("common.saving") : t("knowledgeBases.detail.upload")}
        </Button>
      </div>
      {ingestError ? (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm text-destructive">{translateApiError(t, ingestError)}</p>
          {onRetryWithReplace ? (
            <Button
              size="sm"
              variant="outline"
              onClick={onRetryWithReplace}
              disabled={isIngestPending}
            >
              {t("knowledgeBases.detail.replaceExisting")}
            </Button>
          ) : null}
        </div>
      ) : null}
      {reconvertError ? (
        <p className="text-sm text-destructive">{translateApiError(t, reconvertError)}</p>
      ) : null}
      {docs ? (
        <ul className="divide-y rounded border">
          {docs.documents.map((d: DocumentOut) => (
            <li key={d.id} className="space-y-2 p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{d.title}</span>
                    <Badge variant={d.source_mode === "edited" ? "default" : "secondary"}>
                      {t(`knowledgeBases.sourceMode.${d.source_mode}`)}
                    </Badge>
                  </div>
                  <div className="font-mono text-xs text-muted-foreground">{d.id}</div>
                  <div className="text-xs text-muted-foreground">
                    {t("knowledgeBases.detail.chunks", { count: d.chunk_count ?? 0 })}
                  </div>
                </div>
                {editingId === d.id ? null : (
                  <div className="flex shrink-0 gap-1">
                    {d.source_mode === "converted" ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => onReconvert(d.id)}
                        disabled={isReconvertPending}
                      >
                        {t("knowledgeBases.detail.reconvert")}
                      </Button>
                    ) : null}
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => onStartEdit(d.id)}
                      disabled={isStartEditPending}
                    >
                      {t("common.edit")}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        if (
                          window.confirm(
                            t("knowledgeBases.detail.deleteConfirm", { title: d.title }),
                          )
                        ) {
                          onDelete(d.id);
                        }
                      }}
                      disabled={isDeletePending}
                    >
                      {t("common.delete")}
                    </Button>
                  </div>
                )}
              </div>
              {editingId === d.id ? (
                <div className="space-y-2">
                  <textarea
                    aria-label={t("knowledgeBases.detail.editAria", { title: d.title })}
                    className="min-h-48 w-full rounded-md border border-input bg-background p-2 font-mono text-xs"
                    value={editText}
                    onChange={(e) => onEditTextChange(e.target.value)}
                  />
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      onClick={() => onSaveEdit(d.id)}
                      disabled={!editText.trim() || isEditPending}
                    >
                      {isEditPending ? t("common.saving") : t("common.save")}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={onCancelEdit}>
                      {t("common.cancel")}
                    </Button>
                  </div>
                </div>
              ) : null}
            </li>
          ))}
          {docs.documents.length === 0 ? (
            <li className="p-3 text-sm text-muted-foreground">
              {t("knowledgeBases.detail.empty")}
            </li>
          ) : null}
        </ul>
      ) : null}
    </section>
  );
}
