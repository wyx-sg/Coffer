// frontend/src/components/skills/SkillTreeNodes.tsx
// The rows of a skill folder's file tree (canvas 4.3.12, Foundations 0.6.04):
// no root row, SKILL.md first, then folders, then the other files. A row is the
// shared tree row (knowledge/navRow.ts) — a folder's name in the sans face and
// a file's in the mono face, 16px an indent a level, the open file filled. A
// file with unsaved edits wears a 7px accent dot at its right; in a read-only
// folder every file wears a lock there instead.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen, Lock } from "lucide-react";

import {
  NAV_CHEVRON,
  NAV_FOLDER,
  NAV_ICON,
  NAV_NAME,
  NAV_ROW,
  NAV_ROW_ACTIVE,
  NAV_ROW_IDLE,
  navIndent,
} from "@/components/knowledge/navRow";
import type { SkillFileNode } from "@/lib/api/skills";
import { sortSkillNodes } from "@/lib/skills/tree";
import { cn } from "@/lib/utils";

interface NodeProps {
  node: SkillFileNode;
  depth: number;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  /** The file whose draft is unsaved, marked with a dot. */
  dirtyPath?: string | null;
  /** Every file is read-only: each wears a lock. */
  readOnly?: boolean;
}

export function SkillTreeNode({
  node,
  depth,
  selectedPath,
  onSelectFile,
  dirtyPath = null,
  readOnly = false,
}: NodeProps) {
  const { t } = useTranslation();
  // The folders on the way to the open file start open, the rest shut.
  const [expanded, setExpanded] = useState(
    depth < 1 || Boolean(selectedPath?.startsWith(`${node.path}/`)),
  );
  const indent = navIndent(depth);

  if (node.type === "dir") {
    const children = sortSkillNodes(node.children ?? []);
    return (
      <li>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          style={indent}
          aria-expanded={expanded}
          className={cn(NAV_ROW, NAV_ROW_IDLE)}
        >
          <span className={NAV_CHEVRON}>
            {expanded ? (
              <ChevronDown className="size-3" aria-hidden />
            ) : (
              <ChevronRight className="size-3" aria-hidden />
            )}
          </span>
          {expanded ? (
            <FolderOpen className={NAV_ICON} aria-hidden />
          ) : (
            <Folder className={NAV_ICON} aria-hidden />
          )}
          <span className={NAV_FOLDER}>{node.name}</span>
        </button>
        {expanded && children.length > 0 ? (
          <ul className="flex flex-col gap-px">
            {children.map((child) => (
              <SkillTreeNode
                key={child.path}
                node={child}
                depth={depth + 1}
                selectedPath={selectedPath}
                onSelectFile={onSelectFile}
                dirtyPath={dirtyPath}
                readOnly={readOnly}
              />
            ))}
          </ul>
        ) : null}
      </li>
    );
  }

  const active = selectedPath === node.path;
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelectFile(node.path)}
        style={indent}
        aria-current={active ? "true" : undefined}
        className={cn(NAV_ROW, active ? NAV_ROW_ACTIVE : NAV_ROW_IDLE)}
      >
        <span className={NAV_CHEVRON} />
        <FileText className={NAV_ICON} aria-hidden />
        <span className={cn(NAV_NAME, active && "font-label")}>{node.name}</span>
        {dirtyPath === node.path ? (
          <span
            role="img"
            aria-label={t("skills.files.unsavedDot")}
            className="size-[7px] shrink-0 rounded-full bg-accent"
          />
        ) : readOnly ? (
          <Lock className="size-[13px] shrink-0 text-text-subtle" aria-hidden />
        ) : null}
      </button>
    </li>
  );
}
