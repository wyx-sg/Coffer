// frontend/src/components/memory/MemoryFileViewer.tsx
//
// Right pane of the partition file browser: markdown (.md) renders through the
// shared <FindableMarkdown> — which shows a note's frontmatter as metadata
// above its body — and anything else shows raw in <CodeView>.
//
// It only reads. Coffer's own passes own every byte under `~/.coffer/memory/`
// — the distil pass writes `MEMORY.md`, `notes/` and `RETIRED.md` — and they
// rewrite on their own schedule, so an in-app edit would be a change with a
// countdown on it: silently reverted by the next pass, with no way for the
// reader to tell that had happened. The <FileActions> bar is still here:
// opening the file in a real editor is the honest way to change something the
// daemon owns, because the reader then sees the file itself and owns the
// consequence. Hence no draft, no fingerprint, no save.
import { useTranslation } from "react-i18next";

import { FileActions } from "@/components/FileActions";
import { FILE_PANE_BODY } from "@/components/filePane";
import { CodeView } from "@/components/preview/CodeView";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { translateApiError } from "@/lib/api/errors";
import { usePartitionFileContent } from "@/lib/hooks/useMemory";

function isMarkdown(path: string): boolean {
  return /\.mdx?$/i.test(path);
}

export function MemoryFileViewer({ uid, path }: { uid: string; path: string }) {
  const { t } = useTranslation();
  const content = usePartitionFileContent(uid, path);

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

  // Path on the first row, the open/reveal actions on a second row below —
  // mirrors the skill file viewer so the two file previews read the same.
  const header = (
    <div className="shrink-0 space-y-2">
      <span className="block truncate font-mono text-xs text-muted-foreground">{path}</span>
      {absPath ? <FileActions filePath={absPath} /> : null}
    </div>
  );

  if (content.data?.binary) {
    return (
      <div className={FILE_PANE_BODY}>
        {header}
        <div className="flex min-h-0 flex-1 items-center justify-center rounded border border-dashed text-sm text-muted-foreground">
          {t("memory.files.binary", { size: content.data.size })}
        </div>
      </div>
    );
  }

  const text = content.data?.content ?? "";
  const truncated = content.data?.truncated ?? false;

  return (
    <div className={FILE_PANE_BODY}>
      {header}

      {/* The preview takes the rest of the pane, down to the bottom of the
          window, and scrolls inside (components/filePane.ts). */}
      {isMarkdown(path) ? (
        <FindableMarkdown fill className="rounded border bg-background p-3">
          {text}
        </FindableMarkdown>
      ) : (
        <CodeView value={text} filename={path} fill className="bg-background" />
      )}

      {truncated ? (
        <p className="shrink-0 text-xs text-muted-foreground">{t("memory.files.truncated")}</p>
      ) : null}
    </div>
  );
}
