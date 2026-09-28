// frontend/src/components/knowledge/KnowledgeFilePreview.tsx
//
// The pane beside a collection's tree: one document, with what may be done to
// it (spec knowledge "Present a collection as one tree in the web UI"). It
// works like the skill viewer (`SkillFileViewer`): the document renders by
// default, and an explicit Edit turns it into the shared `FileEditor` with
// Save and Cancel (see "Save a document edited in the web UI"). The save sends
// the body only — the frontmatter stays as it is on disk — with the
// fingerprint the read carried, so a file that changed underneath the editor
// is refused and the draft survives with a discard-and-reload way out. Every
// document is the same here, whoever wrote it last: it can be edited, handed
// to the user's own editor, revealed in their file manager, and deleted (see
// "Let only a person delete a document").
//
// An inbox item (`inbox: true`) is material still waiting to be merged: it can
// be read, never edited or deleted, and the pane says why instead of offering
// either.
//
// `curated_at` says when a curation pass last had the document in front of
// it. A document edited since is what the sweep comes back for, so the line
// answers "has Coffer seen my change yet?" by comparing it with the edit.
import { useTranslation } from "react-i18next";

import { FileActions } from "@/components/FileActions";
import { FileEditor } from "@/components/FileEditor";
import { FILE_PANE_BODY } from "@/components/filePane";
import { KnowledgeFileDelete } from "@/components/knowledge/KnowledgeFileDelete";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { FileOut } from "@/lib/api/knowledge";
import { useFileDraft } from "@/lib/hooks/useFileDraft";
import { useKnowledgeFile, useSaveKnowledgeFile } from "@/lib/hooks/useKnowledge";
import { cn, formatDateTime } from "@/lib/utils";

interface Props {
  /** Knowledge-root-relative path of the file on screen, `null` for none. */
  path: string | null;
  /** Called once the document has been removed, so the page can leave the pane. */
  onDeleted: () => void;
}

/** The pane fills its grid cell (components/filePane.ts): a flex column whose
 *  header row stays put while the body scrolls. */
const PANE = "flex min-h-0 min-w-0 flex-col rounded-md border";

export function KnowledgeFilePreview({ path, onDeleted }: Props) {
  const { t } = useTranslation();
  const file = useKnowledgeFile(path);

  if (path === null) {
    return (
      <section className={PANE}>
        <p className="p-6 text-sm text-muted-foreground">{t("knowledge.detail.selectAFile")}</p>
      </section>
    );
  }
  if (file.isPending) {
    return (
      <section className={cn(PANE, "gap-3 p-4")} aria-busy>
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-2/3" />
      </section>
    );
  }
  if (file.error) {
    return (
      <section className={PANE}>
        <p className="p-6 text-sm text-destructive" role="alert">
          {translateApiError(t, file.error)}
        </p>
      </section>
    );
  }

  // Keyed by path: a draft belongs to one document, and must not carry over
  // to the next one opened — even one whose body happens to be identical.
  return (
    <KnowledgeDocument
      key={file.data.path}
      data={file.data}
      reload={() => file.refetch()}
      onDeleted={onDeleted}
    />
  );
}

function KnowledgeDocument({
  data,
  reload,
  onDeleted,
}: {
  data: FileOut;
  reload: () => Promise<unknown>;
  onDeleted: () => void;
}) {
  const { t } = useTranslation();
  const saveFile = useSaveKnowledgeFile();
  const draft = useFileDraft({
    loaded: data.body,
    fingerprint: data.fingerprint,
    save: (body, expectedFingerprint) =>
      saveFile({ path: data.path, body, expected_fingerprint: expectedFingerprint ?? "" }),
    reload,
  });

  return (
    <section className={PANE}>
      <div className="flex shrink-0 items-center justify-between gap-3 border-b px-4 py-2">
        <div className="min-w-0">
          <p className="truncate text-sm text-muted-foreground">{data.path}</p>
          <p className="truncate text-xs text-muted-foreground">
            {data.curated_at
              ? t("knowledge.detail.curatedAt", { when: formatDateTime(data.curated_at) })
              : t("knowledge.detail.notCuratedYet")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FileActions filePath={data.file_path} />
          {/* Last, after the actions that take the file elsewhere — the same
              order every detail page puts delete in. It names the document
              being previewed, which is the one path the page knows for
              certain. An inbox item is not the person's to delete: curation
              drains it. */}
          {data.inbox ? null : <KnowledgeFileDelete path={data.path} onDeleted={onDeleted} />}
        </div>
      </div>
      {/* The editor takes the rest of the pane, down to the bottom of the
          window; the rendered body inside it scrolls — both axes, which is
          also what keeps a wide table or an unbreakable code span from
          stretching the grid column and scrolling the whole page sideways. */}
      <div className={cn(FILE_PANE_BODY, "px-4 pt-2 pb-4")}>
        <FileEditor
          value={draft.value}
          onChange={draft.setDraft}
          editing={draft.editing}
          dirty={draft.dirty}
          saving={draft.saving}
          error={draft.error}
          conflict={draft.conflict}
          onEdit={draft.startEditing}
          onCancel={draft.cancel}
          onSave={draft.save}
          onDiscardAndReload={() => void draft.discardAndReload()}
          readOnlyReason={data.inbox ? t("knowledge.detail.inboxReadOnly") : null}
          ariaLabel={t("knowledge.detail.editorLabel", { path: data.path })}
          fill
        >
          <FindableMarkdown fill>{data.body}</FindableMarkdown>
        </FileEditor>
      </div>
    </section>
  );
}
