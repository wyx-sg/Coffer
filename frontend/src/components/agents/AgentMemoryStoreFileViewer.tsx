// frontend/src/components/agents/AgentMemoryStoreFileViewer.tsx — spec agent-registry
// "Read one native memory store's files read-only".
//
// Right pane of the native-memory store browser: the file's name marked
// Read-only (and, for the index, what it is), open-in-editor / reveal, the
// content — markdown through <FindableMarkdown>, anything else raw in
// <CodeView> — and a footer saying who owns the file, with its absolute path.
//
// It only reads. These files belong to the coding agent, which rewrites them
// whenever it learns something, so an in-app edit would be silently reverted
// by the agent's next pass. Opening the file in a real editor is the honest way
// to change something another process owns — hence no draft and no save.
import { useTranslation } from "react-i18next";

import { LoadError } from "@/components/LoadError";
import { FileActions } from "@/components/FileActions";
import { FILE_PANE_BODY } from "@/components/filePane";
import { CodeView } from "@/components/preview/CodeView";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { abbreviateHomePath } from "@/lib/agents/display";
import { useNativeMemoryFileContent } from "@/lib/hooks/useAgentNativeMemory";

function isMarkdown(path: string): boolean {
  return /\.mdx?$/i.test(path);
}

const QUIET =
  "flex min-h-0 flex-1 items-center justify-center rounded-md border border-dashed text-sm text-text-muted";

export function AgentMemoryStoreFileViewer({
  agentUid,
  dir,
  path,
  agentName,
}: {
  agentUid: string;
  dir: string;
  path: string;
  agentName: string;
}) {
  const { t } = useTranslation();
  const content = useNativeMemoryFileContent(agentUid, dir, path);

  if (content.isPending) {
    return <p className="text-sm text-text-muted">{t("common.loading")}</p>;
  }
  if (content.error) {
    return <LoadError error={content.error} onRetry={() => void content.refetch()} />;
  }

  const data = content.data;
  const absPath = data?.abs_path;
  const name = path.split("/").pop() ?? path;
  const text = data?.content ?? "";

  return (
    <div className={FILE_PANE_BODY}>
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-baseline gap-2">
            <span className="break-all font-mono text-sm font-medium text-text">{name}</span>
            <span className="text-2xs text-text-subtle">{t("agents.memoryStore.readOnly")}</span>
          </p>
          {name === "MEMORY.md" ? (
            <p className="mt-0.5 text-xs text-text-muted">
              {t("agents.memoryStore.indexHint", { agent: agentName })}
            </p>
          ) : null}
        </div>
        {absPath ? <FileActions filePath={absPath} /> : null}
      </div>

      {data?.binary ? (
        <div className={QUIET}>{t("agents.memoryStore.binary", { size: data.size })}</div>
      ) : isMarkdown(path) ? (
        <FindableMarkdown fill className="rounded-md border bg-background p-3">
          {text}
        </FindableMarkdown>
      ) : (
        <CodeView value={text} filename={path} fill className="bg-background" />
      )}

      <div className="shrink-0 space-y-0.5 text-2xs text-text-subtle">
        {data?.truncated ? <p>{t("agents.memoryStore.truncated")}</p> : null}
        <p>{t("agents.memoryStore.ownedBy", { agent: agentName })}</p>
        {absPath ? <p className="break-all font-mono">{abbreviateHomePath(absPath)}</p> : null}
      </div>
    </div>
  );
}
