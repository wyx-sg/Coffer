// frontend/src/components/skills/SkillFileViewer.tsx
// The right half of the Files tab card (canvas 4.3.01, 4.3.12–4.3.16;
// Foundations 0.6.03): the 40px toolbar — the file's path under the skill's
// name, its size, and the actions — over the file.
//
// - SKILL.md and other Markdown open rendered, its front matter a key / value
//   block above the title, with a Preview / Source switch and Edit.
// - Code files show their text with line numbers, a wrap toggle and Edit.
// - Editing is an explicit mode (SkillFileEditing): Cancel and Save, ⌘S saves,
//   and a save refused because the file changed on disk keeps the text and
//   offers Compare… and Copy my text.
// - A binary file says it can't be previewed and offers Reveal in Finder.
// - A file too large to read whole shows its start, read-only, under a grey bar
//   with Open in editor; agents still get all of it.
// - Every file of the built-in skill is read-only: Coffer rewrites that folder
//   at every start (spec skill-manager "Regenerate Coffer's builtin skill from
//   the build").
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil } from "lucide-react";

import { SkillFileEditing } from "@/components/skills/SkillFileEditing";
import { FileBody } from "@/components/files/FileBody";
import { BinaryPane, TruncatedBar } from "@/components/files/FileStates";
import { isMarkdownPath } from "@/components/files/middlePath";
import { ViewerToolbar, type FileView } from "@/components/files/ViewerToolbar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { useFsActions } from "@/lib/fsActions";
import { useFileDraft } from "@/lib/hooks/useFileDraft";
import { useSkillFileContent, useWriteSkillFile } from "@/lib/hooks/useSkills";
import { usePreferredEditor } from "@/lib/preferences";

interface Props {
  uid: string;
  /** The skill's name: the toolbar's path starts with it, and the unsaved-changes dialog names it. */
  owner: string;
  path: string;
  builtin?: boolean;
  /** Told when the file gains or loses unsaved edits, for the tree's dot. */
  onDirtyChange?: (dirty: boolean) => void;
}

export function SkillFileViewer({ uid, owner, path, builtin = false, onDirtyChange }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const editor = usePreferredEditor();
  const fs = useFsActions();
  const content = useSkillFileContent(uid, path);
  const write = useWriteSkillFile(uid);
  const [view, setView] = useState<FileView>("preview");
  const [wrap, setWrap] = useState(false);
  const draft = useFileDraft({
    loaded: content.data?.content,
    fingerprint: content.data?.fingerprint,
    save: async (text, expectedFingerprint) => {
      const saved = await write.mutateAsync({
        path,
        content: text,
        // Every vault write compares; with no fingerprint to state, the empty
        // one is refused as stale rather than written blind.
        expected_fingerprint: expectedFingerprint ?? "",
      });
      return saved.fingerprint;
    },
    reload: () => content.refetch(),
    guard: { file: path, owner },
  });
  const dirty = draft.editing && draft.dirty;
  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange]);

  const data = content.data;
  const abs = data?.abs_path ?? null;
  const shownPath = `${owner}/${path}`;
  const openInEditor = () =>
    abs && void fs.open(abs, editor).catch(() => toast.error(t("fileActions.openFailed")));
  const reveal = () =>
    abs && void fs.reveal(abs).catch(() => toast.error(t("fileActions.revealFailed")));

  if (content.isPending) {
    return (
      <>
        <ViewerToolbar path={shownPath} />
        <div className="space-y-2 p-4" aria-busy="true">
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="h-40 w-full" />
        </div>
      </>
    );
  }
  if (content.error || !data) {
    return (
      <>
        <ViewerToolbar path={shownPath} />
        <p className="p-4 text-sm text-danger" role="alert">
          {translateApiError(t, content.error)}
        </p>
      </>
    );
  }

  if (data.binary) {
    return (
      <>
        <ViewerToolbar path={shownPath} size={data.size} />
        <BinaryPane name={path.split("/").pop() ?? path} size={data.size} onReveal={reveal} />
      </>
    );
  }

  if (draft.editing) {
    return (
      <SkillFileEditing
        uid={uid}
        owner={owner}
        path={path}
        draft={draft}
        reload={() => content.refetch()}
      />
    );
  }

  const markdown = isMarkdownPath(path) && !data.truncated;
  const readOnly = builtin || data.truncated;
  return (
    <>
      <ViewerToolbar
        path={shownPath}
        size={data.size}
        view={markdown ? { value: view, onChange: setView } : undefined}
        wrap={markdown ? undefined : { on: wrap, onChange: setWrap }}
      >
        {readOnly ? null : (
          <Button variant="outline" size="sm" onClick={draft.startEditing}>
            <Pencil aria-hidden /> {t("common.edit")}
          </Button>
        )}
      </ViewerToolbar>
      {data.truncated ? (
        <TruncatedBar shown={data.content.length} total={data.size} onOpenInEditor={openInEditor} />
      ) : null}
      <FileBody
        path={path}
        text={data.content}
        view={view}
        wrap={wrap}
        truncated={data.truncated}
      />
    </>
  );
}
