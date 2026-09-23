// frontend/src/components/memory/MemoryFileTree.tsx
//
// Two-pane browser for one partition's own directory under `~/.coffer/memory/`:
// a recursive left tree (expand/collapse dirs, click a file to select it) and a
// right pane that previews the selected file.
//
// A partition IS that folder — `MEMORY.md` is the index, `notes/` holds one
// file per topic, `RETIRED.md` records what left and why, and `.raw/` keeps the
// verbatim entries those notes were distilled from — so showing the folder is
// the most honest surface there is: what the reader sees here is exactly what
// an agent will be handed, with no interpretation layered over it that could
// drift from the bytes on disk. It is deliberately the same component shape as
// the skill Files tab (components/skills/SkillFileTree.tsx); two file browsers
// in one app that look and behave differently teach the reader nothing.
//
// The one thing the tree adds to the raw listing is the distinction it would be
// dangerous to leave implicit: `.raw/` is reachable, but it is marked as
// derived INPUT and it does not open itself, because its files are the agents'
// words rather than Coffer's answer (spec memory "Present partitions as a table
// and a file tree").
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen } from "lucide-react";

import { translateApiError } from "@/lib/api/errors";
import { FILE_PANE_MAX_HEIGHT } from "@/components/filePane";
import { MemoryFileViewer } from "@/components/memory/MemoryFileViewer";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { MemoryFileNode } from "@/lib/api/memoryTypes";
import { usePartitionFiles } from "@/lib/hooks/useMemory";
import { isDerivedInput } from "@/lib/memory/derived";
import { cn } from "@/lib/utils";

export function MemoryFileTree({ uid }: { uid: string }) {
  const { t } = useTranslation();
  const tree = usePartitionFiles(uid);
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
          <MemoryFileViewer uid={uid} path={selectedPath} />
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
  const { t } = useTranslation();
  // The server answers this (`FileNodeOut.derived`); the path convention is the
  // fallback, so a fixture or an older response still marks `.raw/` correctly.
  const derived = node.derived ?? isDerivedInput(node.path);
  // Root + its immediate children start expanded so the tree is useful at a
  // glance — except `.raw/`, which stays shut: it is reachable, not on offer.
  // Opening it by default would put the agents' own words in front of the
  // reader before Coffer's, which is the wrong way round.
  const [expanded, setExpanded] = useState(depth < 2 && !derived);
  const indent = { paddingLeft: `${depth * 0.75 + 0.25}rem` };

  if (node.type === "dir") {
    return (
      <li>
        <div className="flex items-center gap-1.5 pr-2">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            style={indent}
            aria-expanded={expanded}
            className="flex min-w-0 flex-1 items-center gap-1.5 rounded-md py-1.5 text-left text-sm transition-colors hover:bg-secondary hover:text-foreground"
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
          {derived ? <DerivedInputBadge label={t("memory.files.derivedBadge")} /> : null}
        </div>
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
          // A file inside `.raw/` reads as the input it is, not as a note.
          derived && selectedPath !== node.path && "text-muted-foreground",
        )}
      >
        <span className="size-3.5 shrink-0" />
        <FileText className="size-4 shrink-0 opacity-70" />
        <span className="truncate">{node.name}</span>
      </button>
    </li>
  );
}

/** The mark `.raw/` carries in the tree. The sentence behind it is in the
 *  tooltip and again, in full, over any file opened out of that folder. */
function DerivedInputBadge({ label }: { label: string }) {
  const { t } = useTranslation();
  return (
    <Tooltip>
      {/* The span is the trigger, not the Badge: Badge is a plain function
          component, so Radix has nothing to anchor to if it is handed the ref.
          `tabIndex` keeps the hint reachable from the keyboard. */}
      <TooltipTrigger asChild>
        <span tabIndex={0} className="inline-flex shrink-0 rounded-full">
          <Badge
            variant="outline"
            data-testid="memory-derived-badge"
            className="cursor-default border-status-warn/40 text-status-warn"
          >
            {label}
          </Badge>
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{t("memory.files.derivedHint")}</TooltipContent>
    </Tooltip>
  );
}
