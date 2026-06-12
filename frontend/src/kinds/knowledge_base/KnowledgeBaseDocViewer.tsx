// frontend/src/kinds/knowledge_base/KnowledgeBaseDocViewer.tsx
//
// Right-hand preview/editor for the selected KB document. Shows the rendered
// Markdown source read-only; Edit swaps in a textarea (sets source_mode=edited
// on save). Reconvert (converted docs only) re-runs conversion from the raw
// original; Delete removes the document. State + mutations live in the page.
import { useTranslation } from "react-i18next";
import { Pencil, RefreshCw, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import type { DocumentDetailOut } from "./api";

interface Props {
  doc: DocumentDetailOut | undefined;
  isLoading: boolean;
  editing: boolean;
  editText: string;
  isEditPending: boolean;
  isReconvertPending: boolean;
  isDeletePending: boolean;
  reconvertError: unknown;
  onStartEdit: () => void;
  onEditTextChange: (value: string) => void;
  onSave: () => void;
  onCancel: () => void;
  onReconvert: () => void;
  onDelete: () => void;
}

export function KnowledgeBaseDocViewer({
  doc,
  isLoading,
  editing,
  editText,
  isEditPending,
  isReconvertPending,
  isDeletePending,
  reconvertError,
  onStartEdit,
  onEditTextChange,
  onSave,
  onCancel,
  onReconvert,
  onDelete,
}: Props) {
  const { t } = useTranslation();

  if (!doc && !isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center rounded-md border border-dashed border-border">
        <p className="text-sm text-muted-foreground">{t("knowledgeBases.detail.selectDocument")}</p>
      </div>
    );
  }

  if (!doc) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center rounded-md border border-border">
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      </div>
    );
  }

  const canReconvert = doc.source_mode !== "edited";

  return (
    <div className="rounded-md border border-border">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-medium">{doc.title}</span>
          <Badge variant="outline">
            {t(`knowledgeBases.sourceMode.${doc.source_mode}`, { defaultValue: doc.source_mode })}
          </Badge>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {editing ? (
            <>
              <Button size="sm" onClick={onSave} disabled={isEditPending}>
                {t("knowledgeBases.detail.save")}
              </Button>
              <Button size="sm" variant="ghost" onClick={onCancel} disabled={isEditPending}>
                {t("knowledgeBases.detail.cancel")}
              </Button>
            </>
          ) : (
            <>
              <Button size="sm" variant="outline" onClick={onStartEdit}>
                <Pencil className="mr-1.5 size-3.5" /> {t("knowledgeBases.detail.edit")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={onReconvert}
                disabled={!canReconvert || isReconvertPending}
              >
                <RefreshCw className="mr-1.5 size-3.5" /> {t("knowledgeBases.detail.reconvert")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
                onClick={onDelete}
                disabled={isDeletePending}
              >
                <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
              </Button>
            </>
          )}
        </div>
      </div>

      {reconvertError ? (
        <p className="px-4 pt-2 text-sm text-destructive" role="alert">
          {translateApiError(t, reconvertError)}
        </p>
      ) : null}

      {editing ? (
        <textarea
          value={editText}
          onChange={(e) => onEditTextChange(e.target.value)}
          className="h-[55vh] w-full resize-none border-0 bg-transparent p-4 font-mono text-sm focus:outline-none"
          spellCheck={false}
        />
      ) : (
        <pre className="max-h-[55vh] overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-sm">
          {doc.markdown}
        </pre>
      )}
    </div>
  );
}
