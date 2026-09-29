// frontend/src/components/memory/MemoryFileTree.tsx
//
// Two-pane browser for one partition's own directory under `~/.coffer/memory/`:
// a recursive left tree (expand/collapse dirs, click a file to select it) and a
// right pane that previews the selected file.
//
// A partition IS that folder — `MEMORY.md` is the index, `notes/` holds one
// file per topic, and `RETIRED.md` records what left and why — so showing the
// folder is the most honest surface there is: what the reader sees here is
// exactly what an agent will be handed, with no interpretation layered over it
// that could drift from the bytes on disk. It is deliberately the same
// component shape as the skill Files tab (components/skills/SkillFileTree.tsx);
// two file browsers in one app that look and behave differently teach the
// reader nothing.
//
// The verbatim entries those notes were distilled from (`.raw/`) are not in the
// tree at all: the server leaves them out, because they are the input to
// Coffer's answer rather than the answer (spec memory "Present partitions as a
// table and a file tree").
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen } from "lucide-react";

import { translateApiError } from "@/lib/api/errors";
import {
  FILE_PANE_COLUMN,
  FILE_PANE_GRID,
  FILE_PANE_SCROLL,
  useFillToBottom,
} from "@/components/filePane";
import { MemoryFileViewer } from "@/components/memory/MemoryFileViewer";
import type { MemoryFileNode } from "@/lib/api/memoryTypes";
import { usePartitionFiles } from "@/lib/hooks/useMemory";
import { cn } from "@/lib/utils";

export function MemoryFileTree({ uid }: { uid: string }) {
  const { t } = useTranslation();
  const tree = usePartitionFiles(uid);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const fill = useFillToBottom();

  return (
    <div
      ref={fill.ref}
      style={fill.style}
      className={cn(FILE_PANE_GRID, "md:grid-cols-[18rem_minmax(0,1fr)]")}
    >
      {/* Left: the recursive file tree. */}
      <div className={FILE_PANE_COLUMN}>
        <p className="shrink-0 px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t("memory.files.tree")}
        </p>
        {tree.isPending ? (
          <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : tree.error ? (
          <p className="px-1 text-sm text-destructive">{translateApiError(t, tree.error)}</p>
        ) : tree.data ? (
          <ul className={cn("space-y-0.5", FILE_PANE_SCROLL)}>
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
      <div className={FILE_PANE_COLUMN}>
        {selectedPath ? (
          <MemoryFileViewer uid={uid} path={selectedPath} />
        ) : (
          <div className="flex min-h-0 flex-1 items-center justify-center rounded border border-dashed text-sm text-muted-foreground">
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
            ? "bg-surface-selected text-text"
            : "hover:bg-surface-hover hover:text-text",
        )}
      >
        <span className="size-3.5 shrink-0" />
        <FileText className="size-4 shrink-0 opacity-70" />
        <span className="truncate">{node.name}</span>
      </button>
    </li>
  );
}
