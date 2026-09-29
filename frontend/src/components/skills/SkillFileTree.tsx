// frontend/src/components/skills/SkillFileTree.tsx
// Two-pane file browser for a skill folder (the Files tab): a recursive left
// tree (expand/collapse dirs, click a file to select it) and a right content
// pane. `SkillFileBrowser` is the shape, fed a tree query and a renderer for the
// selected file; `SkillFileTree` binds it to a managed skill's master folder,
// whose viewer (SkillFileViewer) renders Markdown nicely, shows other text files
// raw, and edits behind an explicit Edit — except a builtin skill's, which it
// keeps read-only because Coffer rewrites them at every start. The unmanaged
// preview (UnmanagedSkillFiles) binds the same browser to a read-only viewer.
// Mirrors the AgentConfigFilesEditor layout.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen } from "lucide-react";

import {
  FILE_PANE_COLUMN,
  FILE_PANE_GRID,
  FILE_PANE_SCROLL,
  useFillToBottom,
} from "@/components/filePane";
import { SkillFileViewer } from "@/components/skills/SkillFileViewer";
import { translateApiError } from "@/lib/api/errors";
import type { SkillFileNode } from "@/lib/api/skills";
import { useSkillFiles } from "@/lib/hooks/useSkills";
import { cn } from "@/lib/utils";

export function SkillFileTree({ uid, builtin = false }: { uid: string; builtin?: boolean }) {
  const tree = useSkillFiles(uid);
  return (
    <SkillFileBrowser
      tree={tree}
      renderFile={(path) => <SkillFileViewer uid={uid} path={path} builtin={builtin} />}
    />
  );
}

/** The tree query's state, whichever route it came from. */
export interface SkillFileTreeQuery {
  isPending: boolean;
  error: unknown;
  data: SkillFileNode | undefined;
}

export function SkillFileBrowser({
  tree,
  renderFile,
}: {
  tree: SkillFileTreeQuery;
  renderFile: (path: string) => ReactNode;
}) {
  const { t } = useTranslation();
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
          {t("skills.files.tree")}
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

      {/* Right: content of the selected file. */}
      <div className={FILE_PANE_COLUMN}>
        {selectedPath ? (
          renderFile(selectedPath)
        ) : (
          <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
            {t("skills.files.selectFile")}
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
  node: SkillFileNode;
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
