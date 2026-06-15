// frontend/src/components/skills/SkillFileViewer.tsx
// Right pane of the skill Files tab: shows the selected file's contents and
// lets the user edit them. Markdown (.md) renders via the shared <Markdown>
// component in read mode; other text files show as raw <pre>. "Edit" swaps in a
// textarea of the raw source (Save writes it back, Cancel discards) — mirroring
// the KB document viewer's edit/save pattern. Binary and truncated files are
// read-only (editing a truncated file would drop everything past the cap).
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil } from "lucide-react";

import { Markdown } from "@/components/Markdown";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import { useSkillFileContent, useWriteSkillFile } from "@/lib/hooks/useSkills";

function isMarkdown(path: string): boolean {
  return /\.mdx?$/i.test(path);
}

export function SkillFileViewer({ name, path }: { name: string; path: string }) {
  const { t } = useTranslation();
  const content = useSkillFileContent(name, path);
  const write = useWriteSkillFile(name);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saved, setSaved] = useState(false);

  // Leave edit mode whenever the selected file changes.
  useEffect(() => {
    setEditing(false);
    setSaved(false);
  }, [path]);

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
  if (content.data?.binary) {
    return (
      <div className="flex h-80 items-center justify-center rounded border border-dashed text-sm text-muted-foreground">
        {t("skills.files.binary", { size: content.data.size })}
      </div>
    );
  }

  const text = content.data?.content ?? "";
  const truncated = content.data?.truncated ?? false;
  const editable = !truncated;

  const startEdit = () => {
    setDraft(text);
    setSaved(false);
    setEditing(true);
  };
  const onSave = () => {
    write.mutate(
      { path, content: draft },
      {
        onSuccess: () => {
          setEditing(false);
          setSaved(true);
        },
      },
    );
  };

  return (
    <div className="space-y-2">
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
          {path}
        </span>
        {editable && !editing ? (
          <Button type="button" variant="outline" size="sm" onClick={startEdit}>
            <Pencil className="mr-1 size-3.5" />
            {t("common.edit")}
          </Button>
        ) : null}
      </div>

      {editing ? (
        <>
          <textarea
            aria-label={path}
            className="h-80 w-full resize-none rounded border bg-background p-2 font-mono text-xs text-foreground"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            spellCheck={false}
          />
          {write.error ? (
            <p role="alert" className="text-xs text-destructive">
              {translateApiError(t, write.error)}
            </p>
          ) : null}
          <div className="flex items-center gap-2">
            <Button type="button" size="sm" onClick={onSave} disabled={write.isPending}>
              {write.isPending ? t("common.saving") : t("common.save")}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setEditing(false)}
              disabled={write.isPending}
            >
              {t("common.cancel")}
            </Button>
          </div>
        </>
      ) : (
        <>
          {isMarkdown(path) ? (
            <div className="h-80 overflow-auto rounded border bg-background p-3">
              <Markdown>{text}</Markdown>
            </div>
          ) : (
            <pre className="h-80 w-full overflow-auto rounded border bg-background p-2 font-mono text-xs text-foreground">
              {text}
            </pre>
          )}
          {truncated ? (
            <p className="text-xs text-muted-foreground">
              {t("skills.files.truncated")} {t("skills.files.truncatedReadonly")}
            </p>
          ) : null}
          {saved ? <p className="text-xs text-muted-foreground">{t("skills.files.saved")}</p> : null}
        </>
      )}
    </div>
  );
}
