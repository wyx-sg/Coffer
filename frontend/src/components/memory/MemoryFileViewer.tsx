// frontend/src/components/memory/MemoryFileViewer.tsx
//
// Right pane of the partition file browser: markdown (.md) renders through the
// shared <FindableMarkdown>, anything else shows raw in <CodeView>.
//
// It only reads. Coffer's own passes own every byte under `~/.coffer/memory/`
// — aggregation writes `.raw/`, the distil pass writes `MEMORY.md`, `notes/`
// and `RETIRED.md` — and both rewrite on their own schedule, so an in-app edit
// would be a change with a countdown on it: silently reverted by the next pass,
// with no way for the reader to tell that had happened. The <FileActions> bar is still here:
// opening the file in a real editor is the honest way to change something the
// daemon owns, because the reader then sees the file itself and owns the
// consequence. Hence no draft, no fingerprint, no save.
import { useTranslation } from "react-i18next";
import { FileInput } from "lucide-react";

import { FileActions } from "@/components/FileActions";
import { CodeView } from "@/components/preview/CodeView";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { translateApiError } from "@/lib/api/errors";
import { usePartitionFileContent } from "@/lib/hooks/useMemory";
import { isDerivedInput } from "@/lib/memory/derived";

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
  //
  // Above both, for a file out of `.raw/`: what this file IS. Everything else
  // in the partition is Coffer's own writing; this one is the agent's, kept so
  // a note can be checked against its source. Said in full here rather than
  // left to the badge in the tree, because the preview is where someone would
  // otherwise read it as Coffer's answer.
  const header = (
    <div className="space-y-2">
      {isDerivedInput(path) ? (
        <Alert variant="warning" data-testid="memory-derived-notice">
          <FileInput className="size-4" aria-hidden />
          <AlertDescription>{t("memory.files.derivedHint")}</AlertDescription>
        </Alert>
      ) : null}
      <span className="block truncate font-mono text-xs text-muted-foreground">{path}</span>
      {absPath ? <FileActions filePath={absPath} /> : null}
    </div>
  );

  if (content.data?.binary) {
    return (
      <div className="space-y-2">
        {header}
        <div className="flex h-80 items-center justify-center rounded border border-dashed text-sm text-muted-foreground">
          {t("memory.files.binary", { size: content.data.size })}
        </div>
      </div>
    );
  }

  const text = content.data?.content ?? "";
  const truncated = content.data?.truncated ?? false;

  return (
    <div className="space-y-2">
      {header}

      {/* Preview grows with content but is capped at 60vh and scrolls inside
          (both axes) — same as the knowledge-base doc viewer, so it never
          exceeds the window and adapts to the window size. */}
      {isMarkdown(path) ? (
        <FindableMarkdown className="max-h-[60vh] overflow-auto rounded border bg-background p-3">
          {text}
        </FindableMarkdown>
      ) : (
        <CodeView value={text} filename={path} maxHeight="60vh" className="bg-background" />
      )}

      {truncated ? (
        <p className="text-xs text-muted-foreground">{t("memory.files.truncated")}</p>
      ) : null}
    </div>
  );
}
