// frontend/src/components/memory/MemoryFileTree.tsx
//
// Two-pane browser for one partition's own directory under `~/.coffer/memory/`:
// a recursive left tree (expand/collapse dirs, click a file to select it) and a
// right pane that previews the selected file.
//
// A partition IS that folder — aggregation writes markdown into it and nothing
// else does — so showing the folder is the most honest surface there is: what
// the reader sees here is exactly what an agent will be handed, with no
// interpretation layered over it that could drift from the bytes on disk. It is
// deliberately the same component shape as the skill Files tab
// (components/skills/SkillFileTree.tsx); two file browsers in one app that look
// and behave differently teach the reader nothing.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen } from "lucide-react";

import { translateApiError } from "@/lib/api/errors";
import { FILE_PANE_MAX_HEIGHT } from "@/components/filePane";
import { MemoryFileViewer } from "@/components/memory/MemoryFileViewer";
import type { MemoryFileNode } from "@/lib/api/memoryTypes";
import { usePartitionFiles } from "@/lib/hooks/useMemory";
import { cn } from "@/lib/utils";

export function MemoryFileTree({ name }: { name: string }) {
  const { t } = useTranslation();
  const tree = usePartitionFiles(name);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  return (
    <div className="grid gap-4 md:grid-cols-[18rem_1fr]">
      {/* Left: the recursive file tree. */}
      <div className="space-y-1">
        <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t("memory.files.tree")}
        </p>
        {tree.isPending ? (
          <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : tree.error ? (
          <p className="px-1 text-sm text-destructive">{translateApiError(t, tree.error)}</p>
        ) : tree.data ? (
          <ul className={cn("space-y-0.5", FILE_PANE_MAX_HEIGHT)}>
            <TreeNode
              node={tree.data}
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
          <MemoryFileViewer name={name} path={selectedPath} />
        ) : (
          <div className="flex h-80 items-center justify-center rounded border border-dashed text-sm text-muted-foreground">
            {t("memory.files.selectFile")}
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
  node: MemoryFileNode;
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
        {expanded && node.children ? (
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
