// frontend/src/components/skills/ReadOnlyFileView.tsx — the file pane of a skill
// folder Coffer does not own (an unmanaged skill, a skill a plugin provides).
//
// Laid out like a managed skill's file pane (SkillFileViewer): a header bar —
// the file's path and size, a Preview / Source switch for Markdown, and a "⋯"
// menu at the right holding Open in editor and Show in Finder — over the file.
// Rendered Markdown (without its frontmatter) for .md/.mdx, a code view
// otherwise, a placeholder for a binary. It only reads: Coffer does not own
// these bytes, so there is no draft, no fingerprint and no save — changing one
// goes through the user's own editor.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { CodeView } from "@/components/preview/CodeView";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { SkillSegmented } from "@/components/skills/SkillSegmented";
import { Skeleton } from "@/components/ui/skeleton";
import { ActionMenu } from "@/components/ui/menu";
import { translateApiError } from "@/lib/api/errors";
import type { SkillFileContentOut } from "@/lib/api/skills";
import { useFileActionItems } from "@/lib/fileActionItems";
import { formatBytes } from "@/lib/utils";

export interface FileContentQuery {
  isPending: boolean;
  error: unknown;
  data: SkillFileContentOut | undefined;
}

function isMarkdown(path: string): boolean {
  return /\.mdx?$/i.test(path);
}

/** The body of a Markdown file, without its leading frontmatter block. */
function withoutFrontmatter(text: string): string {
  return text.replace(/^---\r?\n[\s\S]*?\r?\n---[ \t]*(\r?\n|$)/, "");
}

function Bar({ path, children }: { path: string; children?: ReactNode }) {
  return (
    <div className="flex min-h-12 shrink-0 items-center gap-2 border-b border-border-subtle px-4 py-2">
      <span className="min-w-0 truncate font-mono text-xs font-label text-text">{path}</span>
      {children}
    </div>
  );
}

/** The "⋯" at the bar's right: the file's actions in the user's own tools. */
function FileMenu({ absPath, path }: { absPath: string; path: string }) {
  const { t } = useTranslation();
  const items = useFileActionItems(absPath);
  return (
    <ActionMenu
      label={t("skills.files.moreFor", { path })}
      actions={items.map((it) => ({
        key: it.key,
        label: it.label,
        icon: it.icon,
        onSelect: it.onClick,
      }))}
    />
  );
}

export function ReadOnlyFileView({ path, content }: { path: string; content: FileContentQuery }) {
  const { t } = useTranslation();
  const [view, setView] = useState<"preview" | "source">("preview");

  if (content.isPending) {
    return (
      <>
        <Bar path={path} />
        <div className="space-y-2 p-4" aria-busy="true">
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="h-40 w-full" />
        </div>
      </>
    );
  }
  const data = content.data;
  if (content.error || !data) {
    return (
      <>
        <Bar path={path} />
        <p className="p-4 text-sm text-danger" role="alert">
          {translateApiError(t, content.error)}
        </p>
      </>
    );
  }

  const markdown = isMarkdown(path) && !data.binary && !data.truncated;
  const bar = (
    <Bar path={path}>
      <span className="text-xs text-text-muted">{formatBytes(data.size)}</span>
      <span className="ml-auto flex shrink-0 items-center gap-2">
        {markdown ? (
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
        {data.abs_path ? <FileMenu absPath={data.abs_path} path={path} /> : null}
      </span>
    </Bar>
  );

  if (data.binary) {
    return (
      <>
        {bar}
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-1 p-6 text-center">
          <p className="text-sm font-label text-text">
            {t("skills.files.binaryTitle", { size: formatBytes(data.size) })}
          </p>
          <p className="text-xs text-text-muted">{t("skills.files.binaryBody")}</p>
        </div>
      </>
    );
  }

  return (
    <>
      {bar}
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4">
        {markdown && view === "preview" ? (
          <FindableMarkdown fill frontmatter={false}>
            {withoutFrontmatter(data.content)}
          </FindableMarkdown>
        ) : (
          <CodeView value={data.content} filename={path} fill lineNumbers={data.truncated} />
        )}
        {data.truncated ? (
          <p className="shrink-0 text-xs text-text-muted">{t("skills.files.truncated")}</p>
        ) : null}
      </div>
    </>
  );
}
