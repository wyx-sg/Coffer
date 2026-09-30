// frontend/src/components/knowledge/KnowledgeTreeLevel.tsx
//
// ONE level of a collection's documents, and the recursion that walks it. The
// rows are the same rows the skill Files tab draws (`SkillFileTree`): chevron,
// folder / open-folder or file icon, one truncated line, a depth-proportional
// indent, and the open document filled `bg-surface-selected`. Two file
// browsers that behave the same should look the same.
//
// What is NOT copied is the fetch. A collection descends a level per request,
// so each expanded directory mounts another level and fetches its own listing
// — and directories start CLOSED, except the ones on the way to the open
// document, so a deep link lands with its document visible in the tree.
//
// The collection's `.inbox` is not listed here: it is its own Inbox node above
// the documents (`KnowledgeCollectionNode`), counted and opened as a view of
// its own rather than as a folder.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen } from "lucide-react";

import { NAV_ROW, NAV_ROW_ACTIVE, NAV_ROW_IDLE } from "@/components/knowledge/navRow";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useKnowledgeTree } from "@/lib/hooks/useKnowledge";
import { cn } from "@/lib/utils";

interface Props {
  /** Directory to list, relative to the knowledge root (`shopee` for the
   *  collection itself, `shopee/account` for a folder inside it). */
  path: string;
  /** Nesting depth; drives the indent only (0 = the collection root). */
  depth: number;
  /** Relative path of the open document, if any. */
  selectedPath: string | null;
  onSelect: (path: string) => void;
  /** What an EMPTY collection root says; nested levels say "nothing here". */
  emptyLabel?: string;
}

/** Row indent, matching `SkillFileTree`'s: 0.75rem a level, 0.25rem of gutter. */
function indentOf(depth: number): { paddingLeft: string } {
  return { paddingLeft: `${depth * 0.75 + 0.25}rem` };
}

export function KnowledgeTreeLevel({ path, depth, selectedPath, onSelect, emptyLabel }: Props) {
  const { t } = useTranslation();
  // What the person opened and closed; a folder on the way to the open
  // document is open unless they closed it.
  const [opened, setOpened] = useState<Set<string>>(new Set());
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const { data, isPending, error } = useKnowledgeTree(path);

  if (error) {
    return (
      <p style={indentOf(depth)} className="py-1.5 text-sm text-danger" role="alert">
        {translateApiError(t, error)}
      </p>
    );
  }
  if (isPending) {
    return (
      <div style={indentOf(depth)} className="space-y-2 py-1.5" aria-busy>
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    );
  }

  const directories = data.directories.filter((d) => !d.inbox);
  if (directories.length === 0 && data.files.length === 0) {
    return (
      <p style={indentOf(depth)} className="py-1.5 text-xs text-text-subtle">
        {emptyLabel ?? t("knowledge.tree.emptyFolder")}
      </p>
    );
  }

  const isOpen = (dir: string) =>
    opened.has(dir) || (!closed.has(dir) && Boolean(selectedPath?.startsWith(`${dir}/`)));
  const toggle = (dir: string) => {
    const nowOpen = !isOpen(dir);
    setOpened((prev) => {
      const next = new Set(prev);
      if (nowOpen) next.add(dir);
      else next.delete(dir);
      return next;
    });
    setClosed((prev) => {
      const next = new Set(prev);
      if (nowOpen) next.delete(dir);
      else next.add(dir);
      return next;
    });
  };

  return (
    <ul className="space-y-0.5">
      {directories.map((dir) => {
        const open = isOpen(dir.path);
        return (
          <li key={dir.path}>
            <button
              type="button"
              onClick={() => toggle(dir.path)}
              aria-expanded={open}
              style={indentOf(depth)}
              className={cn(NAV_ROW, NAV_ROW_IDLE)}
            >
              {open ? (
                <ChevronDown className="size-3.5 shrink-0 opacity-70" aria-hidden />
              ) : (
                <ChevronRight className="size-3.5 shrink-0 opacity-70" aria-hidden />
              )}
              {open ? (
                <FolderOpen className="size-4 shrink-0 opacity-70" aria-hidden />
              ) : (
                <Folder className="size-4 shrink-0 opacity-70" aria-hidden />
              )}
              <span className="truncate">{dir.name}</span>
            </button>
            {open ? (
              <KnowledgeTreeLevel
                path={dir.path}
                depth={depth + 1}
                selectedPath={selectedPath}
                onSelect={onSelect}
              />
            ) : null}
          </li>
        );
      })}

      {data.files.map((file) => (
        <li key={file.path}>
          <button
            type="button"
            onClick={() => onSelect(file.path)}
            aria-current={selectedPath === file.path ? "page" : undefined}
            style={indentOf(depth)}
            className={cn(NAV_ROW, selectedPath === file.path ? NAV_ROW_ACTIVE : NAV_ROW_IDLE)}
          >
            {/* The chevron's width, blank, so file rows line up with folders. */}
            <span className="size-3.5 shrink-0" />
            <FileText className="size-4 shrink-0 opacity-70" aria-hidden />
            {/* The frontmatter title: what the document calls itself. */}
            <span className="truncate">{file.title}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
