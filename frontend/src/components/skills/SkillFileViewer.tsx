// frontend/src/components/skills/SkillFileViewer.tsx
// Right pane of the skill Files tab. Reads by default — markdown (.md) renders
// via the shared <Markdown> component, other text files show as raw <pre> —
// and edits behind an explicit Edit, through the same <FileEditor> the agent
// config pane uses. The master folder is the source of truth and
// FOLDER-delivered skills are symlinked to it, so a saved edit reaches every
// agent without re-delivery. The <FileActions> bar still opens / reveals the
// file for edits that want a real editor.
//
// A Markdown file opens rendered; the Preview / Source switch shows its raw
// text instead (spec skill-manager "Cover skill management on REST, the CLI
// and the web", the Files tab).
//
// Binary files, and files the read truncated, stay read-only: saving a partial
// read would cut the file short on disk. So does every file of a builtin skill,
// and it says why — Coffer rewrites that folder at every start, so an edit would
// not survive (spec skill-manager "Regenerate Coffer's builtin skill from the
// build").
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FileActions } from "@/components/FileActions";
import { FileEditor } from "@/components/FileEditor";
import { FILE_PANE_BODY } from "@/components/filePane";
import { CodeView } from "@/components/preview/CodeView";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { SkillSegmented } from "@/components/skills/SkillSegmented";
import { skillsApi } from "@/lib/api/skills";
import { translateApiError } from "@/lib/api/errors";
import { useFileDraft } from "@/lib/hooks/useFileDraft";
import { useSkillFileContent } from "@/lib/hooks/useSkills";

function isMarkdown(path: string): boolean {
  return /\.mdx?$/i.test(path);
}

export function SkillFileViewer({
  uid,
  path,
  builtin = false,
}: {
  uid: string;
  path: string;
  builtin?: boolean;
}) {
  const { t } = useTranslation();
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

  if (content.isPending) {
    return <p className="text-sm text-muted-foreground">{t("common.loading")}</p>;
  }
  if (content.error) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {translateApiError(t, content.error)}
      </p>
    );
  }

  const absPath = content.data?.abs_path;

  // Path on the first row; the open/reveal actions share the editor's action
  // row below it — <FileEditor> renders them left of Edit / Save / Cancel, the
  // same as the agent config viewer (ConfigEditorPane). A binary file has no
  // editor, so it shows the actions on their own.
  const markdown = isMarkdown(path) && !content.data?.binary;
  const header = (
    <div className="flex shrink-0 items-center gap-2">
      <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
        {path}
      </span>
      {markdown && !draft.editing ? (
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
    </div>
  );

  if (content.data?.binary) {
    return (
      <div className={FILE_PANE_BODY}>
        {header}
        {absPath ? (
          <div className="shrink-0">
            <FileActions filePath={absPath} />
          </div>
        ) : null}
        <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
          {t("skills.files.binary", { size: content.data.size })}
        </div>
      </div>
    );
  }

  const text = content.data?.content ?? "";
  const truncated = content.data?.truncated ?? false;

  return (
    <div className={FILE_PANE_BODY}>
      {header}

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
        readOnlyReason={
          builtin ? t("skills.builtinTooltip") : truncated ? t("files.readOnlyTruncated") : null
        }
        ariaLabel={t("skills.files.editorLabel", { path })}
        filePath={absPath}
        fill
      >
        {/* The preview takes the rest of the pane, down to the bottom of the
            window, and scrolls inside (components/filePane.ts). */}
        {markdown && view === "preview" ? (
          <FindableMarkdown fill className="rounded-md border bg-background p-3">
            {text}
          </FindableMarkdown>
        ) : (
          <CodeView value={text} filename={path} fill className="bg-background" />
        )}
      </FileEditor>
      {truncated ? (
        <p className="shrink-0 text-xs text-muted-foreground">
          {t("skills.files.truncated")} {t("skills.files.truncatedReadonly")}
        </p>
      ) : null}
    </div>
  );
}
