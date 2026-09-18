// frontend/src/components/agents/AgentMemoryStoreTree.tsx
//
// Two-pane browser for ONE of the agent's own native memory stores: a recursive
// left tree of the store directory, and a right pane previewing the selected
// file (AgentMemoryStoreFileViewer).
//
// The store IS that directory — Claude Code writes one Markdown file per fact
// into it, Codex keeps one global document — so showing the folder is the most
// honest surface available: what the reader sees here is exactly what the agent
// will be handed, with no interpretation layered over it that could drift from
// the bytes on disk.
//
// Deliberately the same component shape as the skill Files tab
// (components/skills/SkillFileTree.tsx) and the memory partition browser
// (kinds/memory/MemoryFileTree.tsx). It is a fourth instance of that shape
// rather than a shared component those three could import because the
// import-linter-style fence around each kind's frontend folder is the reason
// the third one exists at all — extracting one now would mean editing surfaces
// that belong to other specs. Two file browsers in one app that look and behave
// differently teach the reader nothing, so the shape is what is kept identical.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen } from "lucide-react";

import { FILE_PANE_MAX_HEIGHT } from "@/components/filePane";
import { AgentMemoryStoreFileViewer } from "@/components/agents/AgentMemoryStoreFileViewer";
import { translateApiError } from "@/lib/api/errors";
import type { NativeMemoryFileNode } from "@/lib/api/agentNativeMemory";
import { useNativeMemoryFiles } from "@/lib/hooks/useAgentNativeMemory";
import { cn } from "@/lib/utils";

export function AgentMemoryStoreTree({ agentUid, dir }: { agentUid: string; dir: string }) {
  const { t } = useTranslation();
  const tree = useNativeMemoryFiles(agentUid, dir);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  return (
    <div className="grid gap-4 md:grid-cols-[18rem_1fr]">
      {/* Left: the recursive file tree. */}
      <div className="space-y-1">
        <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t("agents.memoryStore.tree")}
        </p>
        {tree.isPending ? (
          <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : tree.error ? (
          <p className="px-1 text-sm text-destructive">{translateApiError(t, tree.error)}</p>
        ) : tree.data ? (
          <ul className={cn("space-y-0.5", FILE_PANE_MAX_HEIGHT)}>
            <TreeNode
              node={tree.data.root}
              depth={0}
              selectedPath={selectedPath}
              onSelectFile={setSelectedPath}
              isRoot
            />
          </ul>
        ) : null}
      </div>

      {/* Right: read-only content of the selected file. */}
      <div className="min-w-0">
        {selectedPath ? (
          <AgentMemoryStoreFileViewer agentUid={agentUid} dir={dir} path={selectedPath} />
        ) : (
          <div className="flex h-80 items-center justify-center rounded border border-dashed text-sm text-muted-foreground">
            {t("agents.memoryStore.selectFile")}
          </div>
        )}
      </div>
    </div>
  );
}

function TreeNode({
  node,
  depth,
  selectedPath,
  onSelectFile,
  isRoot = false,
}: {
  node: NativeMemoryFileNode;
  depth: number;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  isRoot?: boolean;
}) {
  // Root + its immediate children start expanded so the tree is useful at a glance.
  const [expanded, setExpanded] = useState(depth < 2);
  const indent = { paddingLeft: `${depth * 0.75 + 0.25}rem` };

  if (node.type === "dir") {
    return (
      <li>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          style={indent}
          aria-expanded={expanded}
          className="flex w-full items-center gap-1.5 rounded-md py-1.5 pr-2 text-left text-sm transition-colors hover:bg-secondary hover:text-foreground"
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
          <span className="truncate">{isRoot ? node.name || "/" : node.name}</span>
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
            ? "bg-primary/10 text-primary"
            : "hover:bg-secondary hover:text-foreground",
        )}
      >
        <span className="size-3.5 shrink-0" />
        <FileText className="size-4 shrink-0 opacity-70" />
        <span className="truncate">{node.name}</span>
      </button>
    </li>
  );
}
