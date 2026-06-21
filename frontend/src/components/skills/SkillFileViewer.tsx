// frontend/src/components/skills/SkillFileViewer.tsx
// Right pane of the skill Files tab: shows the selected file's contents
// READ-ONLY. Markdown (.md) renders via the shared <Markdown> component; other
// text files show as raw <pre>. Editing happens in the user's own editor — the
// <FileActions> bar opens / reveals / copies the file's absolute path. Binary
// and truncated files render the same read-only way.
import { useTranslation } from "react-i18next";

import { FileActions } from "@/components/FileActions";
import { CodeView } from "@/components/preview/CodeView";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { translateApiError } from "@/lib/api/errors";
import { useSkillFileContent } from "@/lib/hooks/useSkills";

function isMarkdown(path: string): boolean {
  return /\.mdx?$/i.test(path);
}

export function SkillFileViewer({ name, path }: { name: string; path: string }) {
  const { t } = useTranslation();
  const content = useSkillFileContent(name, path);

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
  const folderAbsPath = content.data?.folder_abs_path;

  const header = (
    <div className="flex flex-wrap items-start justify-between gap-2">
      <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
        {path}
      </span>
      {absPath ? <FileActions filePath={absPath} folderPath={folderAbsPath} /> : null}
    </div>
  );

  if (content.data?.binary) {
    return (
      <div className="space-y-2">
        {header}
        <div className="flex h-80 items-center justify-center rounded border border-dashed text-sm text-muted-foreground">
          {t("skills.files.binary", { size: content.data.size })}
        </div>
      </div>
    );
  }

  const text = content.data?.content ?? "";
  const truncated = content.data?.truncated ?? false;

  return (
    <div className="space-y-2">
      {header}

      {isMarkdown(path) ? (
        <FindableMarkdown className="h-80 overflow-auto rounded border bg-background p-3">
          {text}
        </FindableMarkdown>
      ) : (
        <CodeView value={text} filename={path} height="20rem" className="bg-background" />
      )}
      {truncated ? (
        <p className="text-xs text-muted-foreground">
          {t("skills.files.truncated")} {t("skills.files.truncatedReadonly")}
        </p>
      ) : null}
    </div>
  );
}
