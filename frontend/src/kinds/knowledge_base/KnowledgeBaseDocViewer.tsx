// frontend/src/kinds/knowledge_base/KnowledgeBaseDocViewer.tsx
//
// Right-hand preview for the selected KB document. Renders the Markdown source
// READ-ONLY — editing happens in the user's own editor via the <FileActions>
// bar (open / reveal / copy the absolute path). Reconvert (converted docs only)
// re-runs conversion from the raw original; Delete removes the document. State +
// mutations live in the page.
import { useTranslation } from "react-i18next";
import { Lock, RefreshCw, Trash2, Unlock } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FileActions } from "@/components/FileActions";
import { Markdown } from "@/components/Markdown";
import { translateApiError } from "@/lib/api/errors";
import type { DocumentDetailOut } from "./api";

interface Props {
  doc: DocumentDetailOut | undefined;
  isLoading: boolean;
  isReconvertPending: boolean;
  isDeletePending: boolean;
  isLockPending: boolean;
  reconvertError: unknown;
  onReconvert: () => void;
  onDelete: () => void;
  onToggleLock: () => void;
}

export function KnowledgeBaseDocViewer({
  doc,
  isLoading,
  isReconvertPending,
  isDeletePending,
  isLockPending,
  reconvertError,
  onReconvert,
  onDelete,
  onToggleLock,
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

  // A locked document refuses reconvert/delete server-side (ADR-028); reflect
  // that in the UI by disabling those actions until it is unlocked.
  const canReconvert = doc.source_mode !== "edited" && !doc.locked;

  return (
    <div className="rounded-md border border-border">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-medium">{doc.title}</span>
          <Badge variant="outline">
            {t(`knowledgeBases.sourceMode.${doc.source_mode}`, { defaultValue: doc.source_mode })}
          </Badge>
          {doc.locked ? (
            <Badge variant="outline" className="gap-1 text-amber-600 dark:text-amber-500">
              <Lock className="size-3" /> {t("knowledgeBases.detail.locked")}
            </Badge>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {doc.path ? <FileActions filePath={doc.path} folderPath={doc.folder_path} /> : null}
          <Button
            size="sm"
            variant="outline"
            onClick={onToggleLock}
            disabled={isLockPending}
            title={t(
              doc.locked ? "knowledgeBases.detail.unlockHint" : "knowledgeBases.detail.lockHint",
            )}
          >
            {doc.locked ? (
              <>
                <Unlock className="mr-1.5 size-3.5" /> {t("knowledgeBases.detail.unlock")}
              </>
            ) : (
              <>
                <Lock className="mr-1.5 size-3.5" /> {t("knowledgeBases.detail.lock")}
              </>
            )}
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
            disabled={isDeletePending || doc.locked}
          >
            <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
          </Button>
        </div>
      </div>

      {reconvertError ? (
        <p className="px-4 pt-2 text-sm text-destructive" role="alert">
          {translateApiError(t, reconvertError)}
        </p>
      ) : null}

      <div className="max-h-[60vh] overflow-auto p-4">
        <Markdown>{doc.markdown}</Markdown>
      </div>
    </div>
  );
}
