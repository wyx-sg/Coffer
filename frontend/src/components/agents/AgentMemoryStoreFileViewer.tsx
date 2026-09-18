// frontend/src/components/agents/AgentMemoryStoreFileViewer.tsx
//
// Right pane of the native-memory store browser: markdown (.md) renders through
// the shared <FindableMarkdown>, anything else shows raw in <CodeView>.
//
// It only reads. These files belong to the coding agent, which rewrites them
// whenever it learns something, so an in-app edit would be a change with a
// countdown on it — silently reverted by the agent's next pass, with no way for
// the reader to tell that had happened. The <FileActions> bar is still here:
// opening the file in a real editor is the honest way to change something
// another process owns, because the reader then sees the file itself and owns
// the consequence. Hence no draft, no fingerprint, no save — the same call the
// Coffer memory partition viewer makes for the same reason.
import { useTranslation } from "react-i18next";

import { FileActions } from "@/components/FileActions";
import { CodeView } from "@/components/preview/CodeView";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { translateApiError } from "@/lib/api/errors";
import { useNativeMemoryFileContent } from "@/lib/hooks/useAgentNativeMemory";

function isMarkdown(path: string): boolean {
  return /\.mdx?$/i.test(path);
}

export function AgentMemoryStoreFileViewer({
  agentUid,
  dir,
  path,
}: {
  agentUid: string;
  dir: string;
  path: string;
}) {
  const { t } = useTranslation();
  const content = useNativeMemoryFileContent(agentUid, dir, path);

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
  // mirrors the skill and partition file viewers so every file preview in the
  // app reads the same.
  const header = (
    <div className="space-y-2">
      <span className="block truncate font-mono text-xs text-muted-foreground">{path}</span>
      {absPath ? <FileActions filePath={absPath} /> : null}
    </div>
  );

  if (content.data?.binary) {
    return (
      <div className="space-y-2">
        {header}
        <div className="flex h-80 items-center justify-center rounded border border-dashed text-sm text-muted-foreground">
          {t("agents.memoryStore.binary", { size: content.data.size })}
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
          (both axes), so it never exceeds the window and adapts to its size. */}
      {isMarkdown(path) ? (
        <FindableMarkdown className="max-h-[60vh] overflow-auto rounded border bg-background p-3">
          {text}
        </FindableMarkdown>
      ) : (
        <CodeView value={text} filename={path} maxHeight="60vh" className="bg-background" />
      )}

      {truncated ? (
        <p className="text-xs text-muted-foreground">{t("agents.memoryStore.truncated")}</p>
      ) : null}
    </div>
  );
}
