// frontend/src/components/skills/SkillTreeNodes.tsx
// The rows of a skill folder's file tree: a folder toggles open and shut, a
// file selects itself. `flat` is the Files tab's form (canvas 4.3.01) — no
// root row, SKILL.md first, then folders, then the other files, with a dot on
// the file that has unsaved edits; the unmanaged preview keeps the root row.
import { useState } from "react";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen, Image } from "lucide-react";

import type { SkillFileNode } from "@/lib/api/skills";
import { sortSkillNodes } from "@/lib/skills/tree";
import { cn } from "@/lib/utils";

const IMAGE = /\.(png|jpe?g|gif|svg|webp|ico)$/i;

interface NodeProps {
  node: SkillFileNode;
  depth: number;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  /** The file whose draft is unsaved, marked with a dot. */
  dirtyPath?: string | null;
  isRoot?: boolean;
  flat?: boolean;
}

export function SkillTreeNode({
  node,
  depth,
  selectedPath,
  onSelectFile,
  dirtyPath = null,
  isRoot = false,
  flat = false,
}: NodeProps) {
  // Root + its immediate children start expanded so the tree is useful at a glance.
  const [expanded, setExpanded] = useState(depth < 2);
  const indent = { paddingLeft: `${depth * 0.9 + 0.5}rem` };
  const children = flat ? sortSkillNodes(node.children ?? []) : (node.children ?? []);

  if (node.type === "dir") {
    return (
      <li>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          style={indent}
          aria-expanded={expanded}
          className="flex w-full items-center gap-1.5 rounded-item py-1.5 pr-2 text-left font-mono text-xs transition-colors hover:bg-surface-hover"
        >
          {expanded ? (
            <ChevronDown className="size-3.5 shrink-0 text-text-subtle" />
          ) : (
            <ChevronRight className="size-3.5 shrink-0 text-text-subtle" />
          )}
          {expanded ? (
            <FolderOpen className="size-3.5 shrink-0 text-text-subtle" />
          ) : (
            <Folder className="size-3.5 shrink-0 text-text-subtle" />
          )}
          <span className="truncate">{isRoot ? node.name || "/" : node.name}</span>
        </button>
        {expanded && children.length > 0 ? (
          <ul className="space-y-0.5">
            {children.map((child) => (
              <SkillTreeNode
                key={child.path}
                node={child}
                depth={depth + 1}
                selectedPath={selectedPath}
                onSelectFile={onSelectFile}
                dirtyPath={dirtyPath}
                flat={flat}
              />
            ))}
          </ul>
        ) : null}
      </li>
    );
  }

  const Icon = IMAGE.test(node.name) ? Image : FileText;
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelectFile(node.path)}
        style={indent}
        aria-current={selectedPath === node.path ? "true" : undefined}
        className={cn(
          "flex w-full items-center gap-1.5 rounded-item py-1.5 pr-2 text-left font-mono text-xs transition-colors",
          selectedPath === node.path ? "bg-surface-selected text-text" : "hover:bg-surface-hover",
        )}
      >
        <span className="size-3.5 shrink-0" />
        <Icon className="size-3.5 shrink-0 text-text-subtle" />
        <span className="min-w-0 flex-1 truncate">{node.name}</span>
        {dirtyPath === node.path ? (
          <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-warning" />
        ) : null}
      </button>
    </li>
  );
}
