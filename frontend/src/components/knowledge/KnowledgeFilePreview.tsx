// frontend/src/components/knowledge/KnowledgeFilePreview.tsx
//
// The pane beside a lane's tree: one file, rendered read-only, with the actions
// that file is allowed (spec knowledge FR-040).
//
// Reading is lane-agnostic — a topic document previews exactly as a source
// does. What the LANE decides is what may be done to the file: a source can be
// handed to the user's own editor, revealed, and deleted; a topic document can
// only be opened and revealed, because curation is the only writer of
// `topics/` and the next pass would undo anything else (invariant 2).
//
// `ingested_at` is shown on a source because it answers the one question a
// person has about a note they just wrote: is it in the topics yet?
import { useTranslation } from "react-i18next";

import { FileActions } from "@/components/FileActions";
import { FILE_PANE_MAX_HEIGHT } from "@/components/filePane";
import { KnowledgeFileDelete } from "@/components/knowledge/KnowledgeFileDelete";
import { KnowledgePreviewBody } from "@/components/knowledge/KnowledgePreviewBody";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useKnowledgeFile } from "@/lib/hooks/useKnowledge";
import type { KnowledgeLane } from "@/lib/knowledge/lanes";
import { cn, formatDateTime } from "@/lib/utils";

interface Props {
  /** Knowledge-root-relative path of the file on screen, `null` for none. */
  path: string | null;
  /** Which lane the tree beside this pane is showing. */
  lane: KnowledgeLane;
  /** Called once a source has been removed, so the page can leave the pane. */
  onDeleted: () => void;
}

export function KnowledgeFilePreview({ path, lane, onDeleted }: Props) {
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
          {lane === "sources" ? (
            <p className="truncate text-xs text-muted-foreground">
              {file.data.ingested_at
                ? t("knowledge.detail.curatedAt", {
                    when: formatDateTime(file.data.ingested_at),
                  })
                : t("knowledge.detail.notCuratedYet")}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FileActions filePath={file.data.file_path} />
          {/* Last, after the actions that take the file elsewhere — the same
              order every detail page puts delete in. It is mounted only on a
              SOURCE being previewed, which is what makes the path it names
              certain and keeps `topics/` unreachable from here (FR-020). */}
          {lane === "sources" ? (
            <KnowledgeFileDelete path={file.data.path} onDeleted={onDeleted} />
          ) : null}
        </div>
      </div>
      {/* `overflow-auto` is what keeps a wide table or an unbreakable code span
          inside this pane: without it the content has no scroll container, so
          it stretches the grid column and the whole page scrolls sideways. */}
      <KnowledgePreviewBody text={file.data.body} className={cn(FILE_PANE_MAX_HEIGHT, "p-4")} />
    </section>
  );
}
