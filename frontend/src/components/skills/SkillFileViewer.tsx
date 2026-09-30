// frontend/src/components/skills/SkillFileViewer.tsx
// The right half of the Files tab card (canvas 4.3.01, 4.3.09–4.3.13): a
// header bar — the file's path and size, and its actions — over the file.
//
// - SKILL.md and other Markdown open rendered (without the frontmatter, which
//   the header above the tabs already shows) with a Preview / Source switch
//   and Edit.
// - Other text files show their source with Edit and Open in editor.
// - Editing is an explicit mode (SkillFileEditing): Cancel and Save, ⌘S saves,
//   and a save refused because the file changed on disk keeps the text and
//   offers Reload · Compare · Copy my text, as Knowledge does.
// - A binary file offers Open in default app and Reveal in Finder only.
// - A file too large to read whole shows its start, read-only, with Open in
//   editor; agents still get all of it.
// - Every file of the built-in skill is read-only: Coffer rewrites that folder
//   at every start (spec skill-manager "Regenerate Coffer's builtin skill from
//   the build").
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ExternalLink, FolderOpen, Info, Pencil } from "lucide-react";

import { CodeView } from "@/components/preview/CodeView";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { SkillFileEditing } from "@/components/skills/SkillFileEditing";
import { SkillSegmented } from "@/components/skills/SkillSegmented";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { skillsApi } from "@/lib/api/skills";
import { useFsActions } from "@/lib/fsActions";
import { useFileDraft } from "@/lib/hooks/useFileDraft";
import { useSkillFileContent } from "@/lib/hooks/useSkills";
import { usePreferredEditor } from "@/lib/preferences";
import { formatBytes } from "@/lib/utils";

function isMarkdown(path: string): boolean {
  return /\.mdx?$/i.test(path);
}

/** The body of a Markdown file, without its leading frontmatter block. */
function withoutFrontmatter(text: string): string {
  return text.replace(/^---\r?\n[\s\S]*?\r?\n---[ \t]*(\r?\n|$)/, "");
}

interface Props {
  uid: string;
  path: string;
  builtin?: boolean;
  /** Told when the file gains or loses unsaved edits, for the tree's dot. */
  onDirtyChange?: (dirty: boolean) => void;
}

export function SkillFileViewer({ uid, path, builtin = false, onDirtyChange }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const editor = usePreferredEditor();
  const fs = useFsActions();
  const content = useSkillFileContent(uid, path);
  const [view, setView] = useState<"preview" | "source">("preview");
  const draft = useFileDraft({
    loaded: content.data?.content,
    fingerprint: content.data?.fingerprint,
    save: async (text, expectedFingerprint) => {
      const saved = await skillsApi.writeFileContent(uid, {
        path,
        content: text,
        expected_fingerprint: expectedFingerprint,
      });
      return saved.fingerprint;
    },
    reload: () => content.refetch(),
  });
  const dirty = draft.editing && draft.dirty;
  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange]);

  const data = content.data;
  const abs = data?.abs_path ?? null;
  const openIn = (app: string) =>
    abs && void fs.open(abs, app).catch(() => toast.error(t("fileActions.openFailed")));
  const reveal = () =>
    abs && void fs.reveal(abs).catch(() => toast.error(t("fileActions.revealFailed")));

  const bar = (children: React.ReactNode) => (
    <div className="flex min-h-12 shrink-0 items-center gap-2 border-b border-border-subtle px-4 py-2">
      <span className="min-w-0 truncate font-mono text-xs font-label text-text">{path}</span>
      {children}
    </div>
  );

  if (content.isPending) {
    return (
      <>
        {bar(null)}
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
        {bar(null)}
        <p className="p-4 text-sm text-danger" role="alert">
          {translateApiError(t, content.error)}
        </p>
      </>
    );
  }

  const size = <span className="text-xs text-text-muted">{formatBytes(data.size)}</span>;
  const openInEditor = (
    <Button variant="outline" size="sm" onClick={() => openIn(editor)}>
      <ExternalLink aria-hidden /> {t("fileActions.openInEditor")}
    </Button>
  );

  if (data.binary) {
    return (
      <>
        {bar(
          <>
            {size}
            <span className="ml-auto flex shrink-0 gap-2">
              <Button variant="outline" size="sm" onClick={() => openIn("")}>
                <ExternalLink aria-hidden /> {t("skills.files.openDefault")}
              </Button>
              <Button variant="outline" size="sm" onClick={reveal}>
                <FolderOpen aria-hidden /> {t("fileActions.reveal")}
              </Button>
            </span>
          </>,
        )}
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-1 p-6 text-center">
          <p className="text-sm font-label text-text">
            {t("skills.files.binaryTitle", { size: formatBytes(data.size) })}
          </p>
          <p className="text-xs text-text-muted">{t("skills.files.binaryBody")}</p>
        </div>
      </>
    );
  }

  if (draft.editing) {
    return <SkillFileEditing uid={uid} path={path} draft={draft} />;
  }

  const markdown = isMarkdown(path);
  const readOnly = builtin || data.truncated;
  return (
    <>
      {bar(
        <>
          {size}
          <span className="ml-auto flex shrink-0 items-center gap-2">
            {markdown && !data.truncated ? (
              <SkillSegmented
                label={t("skills.files.viewLabel")}
                value={view}
                onChange={setView}
                options={[
                  { value: "preview", label: t("skills.files.preview") },
                  { value: "source", label: t("skills.files.source") },
                ]}
              />
            ) : null}
            {readOnly ? null : (
              <Button variant="outline" size="sm" onClick={draft.startEditing}>
                <Pencil aria-hidden /> {t("common.edit")}
              </Button>
            )}
            {markdown && !data.truncated ? null : openInEditor}
          </span>
        </>,
      )}
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4">
        {data.truncated ? (
          <Alert variant="info">
            <Info aria-hidden />
            <AlertTitle>
              {t("skills.files.truncatedTitle", { size: formatBytes(data.content.length) })}
            </AlertTitle>
            <AlertDescription>{t("skills.files.truncatedBody")}</AlertDescription>
          </Alert>
        ) : null}
        {markdown && !data.truncated && view === "preview" ? (
          <FindableMarkdown fill frontmatter={false}>
            {withoutFrontmatter(data.content)}
          </FindableMarkdown>
        ) : (
          <CodeView value={data.content} filename={path} fill lineNumbers={data.truncated} />
        )}
      </div>
    </>
  );
}
