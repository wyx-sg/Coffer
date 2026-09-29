// frontend/src/components/agents/AgentMemoryStoreTree.tsx — spec agent-registry
// "Read one native memory store's files read-only".
//
// A resizable split for ONE of the agent's own native memory stores: the store
// directory as a recursive tree ("Files · N") beside a read-only preview of the
// selected file (AgentMemoryStoreFileViewer). The index file (MEMORY.md) opens
// first when the store has one.
//
// The store IS that directory — Claude Code writes one Markdown file per fact
// into it, Codex keeps one global document — so showing the folder is the most
// honest surface available: what the reader sees here is exactly what the agent
// will be handed, with no interpretation layered over it.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen } from "lucide-react";

import { AgentMemoryStoreFileViewer } from "@/components/agents/AgentMemoryStoreFileViewer";
import { FILE_PANE_COLUMN, FILE_PANE_SCROLL, useFillToBottom } from "@/components/filePane";
import { SplitView } from "@/components/SplitView";
import { translateApiError } from "@/lib/api/errors";
import type { NativeMemoryFileNode } from "@/lib/api/agentNativeMemory";
import { countMemoryFiles, useNativeMemoryFiles } from "@/lib/hooks/useAgentNativeMemory";
import { cn } from "@/lib/utils";

export function AgentMemoryStoreTree({
  agentUid,
  dir,
  agentName,
}: {
  agentUid: string;
  dir: string;
  agentName: string;
}) {
  const { t } = useTranslation();
  const tree = useNativeMemoryFiles(agentUid, dir);
  const [picked, setPicked] = useState<string | null>(null);
  const fill = useFillToBottom();
  const root = tree.data?.root;
  // Until the reader picks one, the store's index file is the one to read.
  const index = root?.children.find((c) => c.type === "file" && c.name === "MEMORY.md");
  const selectedPath = picked ?? index?.path ?? null;

  const list = (
    <div className={FILE_PANE_COLUMN}>
      <p className="shrink-0 px-1 text-2xs font-medium uppercase tracking-wide text-text-subtle">
        {root
          ? t("agents.memoryStore.treeCount", { count: countMemoryFiles(root) })
          : t("agents.memoryStore.tree")}
      </p>
      {tree.isPending ? (
        <p className="px-1 text-sm text-text-muted">{t("common.loading")}</p>
      ) : tree.error ? (
        <p className="px-1 text-sm text-danger">{translateApiError(t, tree.error)}</p>
      ) : root ? (
        <ul className={cn("space-y-0.5", FILE_PANE_SCROLL)}>
          {root.children.map((child) => (
            <TreeNode
              key={child.path}
              node={child}
              depth={0}
              selectedPath={selectedPath}
              onSelectFile={setPicked}
            />
          ))}
        </ul>
      ) : null}
    </div>
  );

  const detail = selectedPath ? (
    <AgentMemoryStoreFileViewer
      agentUid={agentUid}
      dir={dir}
      path={selectedPath}
      agentName={agentName}
    />
  ) : (
    <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-dashed text-sm text-text-muted">
      {t("agents.memoryStore.selectFile")}
    </div>
  );

  return (
    <div ref={fill.ref} style={fill.style} className="flex min-h-0">
      <SplitView
        storageKey="agent-memory-store"
        label={t("splitView.resizeList")}
        className="min-h-0 flex-1"
        detailClassName="pl-4"
        list={list}
        detail={detail}
      />
    </div>
  );
}

function TreeNode({
  node,
  depth,
  selectedPath,
  onSelectFile,
}: {
  node: NativeMemoryFileNode;
  depth: number;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
}) {
  // The first level starts open so the tree is useful at a glance.
  const [expanded, setExpanded] = useState(depth < 1);
  const indent = { paddingLeft: `${depth * 0.75 + 0.25}rem` };

  if (node.type === "dir") {
    return (
      <li>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          style={indent}
          aria-expanded={expanded}
          className="flex w-full items-center gap-1.5 rounded-md py-1.5 pr-2 text-left text-sm transition-colors hover:bg-surface-hover hover:text-text"
        >
          {expanded ? (
            <ChevronDown className="size-3.5 shrink-0 opacity-70" />
          ) : (
            <ChevronRight className="size-3.5 shrink-0 opacity-70" />
          )}
          {expanded ? (
            <FolderOpen className="size-4 shrink-0 opacity-70" />
          ) : (
            <Folder className="size-4 shrink-0 opacity-70" />
          )}
          <span className="break-all">{node.name}</span>
        </button>
        {expanded && node.children.length > 0 ? (
          <ul className="space-y-0.5">
            {node.children.map((child) => (
              <TreeNode
                key={child.path}
                node={child}
                depth={depth + 1}
                selectedPath={selectedPath}
                onSelectFile={onSelectFile}
              />
            ))}
          </ul>
        ) : null}
      </li>
    );
  }

  return (
    <li>
      <button
        type="button"
        onClick={() => onSelectFile(node.path)}
        style={indent}
        className={cn(
          "flex w-full items-center gap-1.5 rounded-md py-1.5 pr-2 text-left text-sm transition-colors",
          selectedPath === node.path
            ? "bg-surface-selected text-text"
            : "hover:bg-surface-hover hover:text-text",
        )}
      >
        <span className="size-3.5 shrink-0" />
        <FileText className="size-4 shrink-0 opacity-70" />
        <span className="break-all">{node.name}</span>
      </button>
    </li>
  );
}
