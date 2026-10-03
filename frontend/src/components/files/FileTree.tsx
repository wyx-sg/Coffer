// frontend/src/components/files/FileTree.tsx
//
// The one file tree (Foundations 0.6.04): a 36px header strip (title 13/600, an
// optional lock for a read-only tree, an action at the right), then rows of 28
// — a 12px chevron slot, a 15px icon, folders in the sans face at 13 and files
// in the mono face at 12, a 16px indent a level from an 8px gutter, the open
// row filled `surface-selected`. A file the agent has not created is italic
// with "not created" at its right; the file with unsaved edits carries a small
// accent dot; a read-only tree puts a lock at each row's right.
//
// Pure presentation. The caller flattens its own data into rows (`FileTreeRow`)
// and owns what opening, closing and selecting do; nothing here fetches.
import type { ReactNode } from "react";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen, Lock } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

/** @ui-only One visible row of a tree, already flattened. */
export interface FileTreeRow {
  /** Unique within the tree. */
  key: string;
  name: string;
  kind: "folder" | "file";
  /** 0 = the tree's first level. */
  depth: number;
  /** A folder's state (ignored on a file). */
  open?: boolean;
  /** A folder that has nothing to open — no chevron. */
  leaf?: boolean;
  selected?: boolean;
  /** A file that is not on disk yet: italic, muted, with `note`. */
  missing?: boolean;
  note?: string;
  /** Unsaved edits in this file. */
  dirty?: boolean;
  /** Read-only: a lock at the row's right. */
  locked?: boolean;
  /** Mono for a folder whose name is a path (`~/.claude`), sans is the default. */
  mono?: boolean;
  /** Tooltip. */
  title?: string;
  /** A "⋯" menu at the row's right, shown on hover or focus. */
  menu?: ReactNode;
}

const ROW =
  "flex h-7 min-w-0 flex-1 items-center gap-1.5 rounded-item pr-2 text-left text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring";

function indentOf(depth: number): { paddingLeft: number } {
  return { paddingLeft: 8 + depth * 16 };
}

/** The tree's frame: header strip over a scrolling list. */
export function FileTreePanel({
  title,
  locked,
  action,
  children,
}: {
  title: ReactNode;
  /** A read-only tree: a lock after the title. */
  locked?: boolean;
  /** The header's right end (an icon button). */
  action?: ReactNode;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <>
      <div className="flex h-9 shrink-0 items-center gap-1 border-b border-border-subtle pl-3 pr-2">
        <span className="min-w-0 truncate text-sm font-semibold text-text">{title}</span>
        {locked ? (
          <Lock
            role="img"
            aria-label={t("files.readOnly")}
            className="size-3 shrink-0 text-text-subtle"
          />
        ) : null}
        {action ? <span className="ml-auto inline-flex shrink-0">{action}</span> : null}
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-1.5">{children}</div>
    </>
  );
}

export function FileTree({
  rows,
  label,
  onActivate,
}: {
  rows: readonly FileTreeRow[];
  /** The tree's accessible name. */
  label: string;
  /** A row was clicked (a folder toggles / opens, a file opens). */
  onActivate: (row: FileTreeRow) => void;
}) {
  const { t } = useTranslation();
  return (
    <ul role="tree" aria-label={label} className="flex flex-col gap-px">
      {rows.map((row) => {
        const folder = row.kind === "folder";
        const FolderIcon = row.open ? FolderOpen : Folder;
        return (
          <li
            key={row.key}
            role="none"
            className={cn(
              "group flex items-center rounded-item pr-1 transition-colors",
              row.selected ? "bg-surface-selected" : "hover:bg-surface-hover",
            )}
          >
            <button
              type="button"
              role="treeitem"
              aria-expanded={folder && !row.leaf ? Boolean(row.open) : undefined}
              aria-selected={row.selected ?? false}
              title={row.title}
              style={indentOf(row.depth)}
              className={ROW}
              onClick={() => onActivate(row)}
            >
              <span className="inline-flex w-3 shrink-0 items-center justify-center text-text-subtle">
                {folder && !row.leaf ? (
                  row.open ? (
                    <ChevronDown className="size-3" aria-hidden />
                  ) : (
                    <ChevronRight className="size-3" aria-hidden />
                  )
                ) : null}
              </span>
              {folder ? (
                <FolderIcon className="size-[15px] shrink-0 text-text-subtle" aria-hidden />
              ) : (
                <FileText className="size-[15px] shrink-0 text-text-subtle" aria-hidden />
              )}
              <span
                className={cn(
                  "min-w-0 truncate",
                  folder && !row.mono ? "text-sm" : "font-mono text-xs",
                  row.missing && "italic text-text-subtle",
                  row.selected && !folder && "font-label",
                )}
              >
                {row.name}
              </span>
              {row.missing && row.note ? (
                <span className="ml-auto shrink-0 whitespace-nowrap pl-1 text-2xs text-text-subtle">
                  {row.note}
                </span>
              ) : null}
              {row.dirty ? (
                <span
                  role="img"
                  aria-label={t("files.unsaved")}
                  className="ml-auto size-[7px] shrink-0 rounded-full bg-accent"
                />
              ) : null}
              {row.locked ? (
                <Lock
                  aria-hidden
                  className={cn(
                    "size-3 shrink-0 text-text-subtle",
                    !row.dirty && !(row.missing && row.note) && "ml-auto",
                  )}
                />
              ) : null}
            </button>
            {row.menu ? (
              // A row's menu stays out of the way until the row is hovered or focused.
              <span className="inline-flex shrink-0 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100 has-[[data-state=open]]:opacity-100">
                {row.menu}
              </span>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
