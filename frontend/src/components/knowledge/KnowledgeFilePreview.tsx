// frontend/src/components/knowledge/KnowledgeFilePreview.tsx
//
// The pane beside a collection's tree: one document, rendered read-only, with
// what may be done to it (spec knowledge FR-040). Every document is the same
// here, whoever wrote it last: it can be handed to the user's own editor,
// revealed in their file manager, and deleted (FR-020). Editing happens in
// that editor, never in this pane — the file on disk is the document, and an
// edit there is live on the next read.
//
// `curated_at` says when a curation pass last had the document in front of
// it. A document edited since is what the sweep comes back for, so the line
// answers "has Coffer seen my change yet?" by comparing it with the edit.
import { useTranslation } from "react-i18next";

import { FileActions } from "@/components/FileActions";
import { FILE_PANE_MAX_HEIGHT } from "@/components/filePane";
import { KnowledgeFileDelete } from "@/components/knowledge/KnowledgeFileDelete";
import { KnowledgePreviewBody } from "@/components/knowledge/KnowledgePreviewBody";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useKnowledgeFile } from "@/lib/hooks/useKnowledge";
import { cn, formatDateTime } from "@/lib/utils";

interface Props {
  /** Knowledge-root-relative path of the file on screen, `null` for none. */
  path: string | null;
  /** Called once the document has been removed, so the page can leave the pane. */
  onDeleted: () => void;
}

export function KnowledgeFilePreview({ path, onDeleted }: Props) {
  const { t } = useTranslation();
  const file = useKnowledgeFile(path);

  if (path === null) {
    return (
      <section className="min-w-0 rounded-md border">
        <p className="p-6 text-sm text-muted-foreground">{t("knowledge.detail.selectAFile")}</p>
      </section>
    );
  }
  if (file.isPending) {
    return (
      <section className="min-w-0 space-y-3 rounded-md border p-4" aria-busy>
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-2/3" />
      </section>
    );
  }
  if (file.error) {
    return (
      <section className="min-w-0 rounded-md border">
        <p className="p-6 text-sm text-destructive" role="alert">
          {translateApiError(t, file.error)}
        </p>
      </section>
    );
  }

  return (
    <section className="min-w-0 rounded-md border">
      <div className="flex items-center justify-between gap-3 border-b px-4 py-2">
        <div className="min-w-0">
          <p className="truncate text-sm text-muted-foreground">{file.data.path}</p>
          <p className="truncate text-xs text-muted-foreground">
            {file.data.curated_at
              ? t("knowledge.detail.curatedAt", { when: formatDateTime(file.data.curated_at) })
              : t("knowledge.detail.notCuratedYet")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FileActions filePath={file.data.file_path} />
          {/* Last, after the actions that take the file elsewhere — the same
              order every detail page puts delete in. It names the document
              being previewed, which is the one path the page knows for
              certain. */}
          <KnowledgeFileDelete path={file.data.path} onDeleted={onDeleted} />
        </div>
      </div>
      {/* `overflow-auto` is what keeps a wide table or an unbreakable code span
          inside this pane: without it the content has no scroll container, so
          it stretches the grid column and the whole page scrolls sideways. */}
      <KnowledgePreviewBody text={file.data.body} className={cn(FILE_PANE_MAX_HEIGHT, "p-4")} />
    </section>
  );
}
