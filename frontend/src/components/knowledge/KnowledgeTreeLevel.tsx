// frontend/src/components/knowledge/KnowledgeTreeLevel.tsx
//
// ONE level of a collection's documents, and the recursion that walks it. The
// rows are the Knowledge tree's rows (navRow.ts, boards 5.1.01, 5.1.09):
// chevron, folder / open-folder or file icon, a folder's name in the sans face
// and a file's in the mono face — `port-and-handshake.md`, as it is on disk and
// as an agent reads it — a 16px indent a level, and the open document filled
// `surface-selected`.
//
// What is NOT copied is the fetch. A collection descends a level per request,
// so each expanded directory mounts another level and fetches its own listing
// — and directories start CLOSED, except the ones on the way to the open
// document, so a deep link lands with its document visible in the tree.
//
// At a collection's root its two folders come first, labelled Pages and
// Sources, then any other entry; a waiting source carries a dot and the word
// Waiting (spec knowledge "Show a collection as one tree of read-only documents
// in the web UI").
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen } from "lucide-react";

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
import { StatusDot } from "@/components/status/StatusDot";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useKnowledgeTree } from "@/lib/hooks/useKnowledge";
import { cn } from "@/lib/utils";

interface Props {
  /** Directory to list, relative to the knowledge root (`shopee` for the
   *  collection itself, `shopee/account` for a folder inside it). */
  path: string;
  /** Nesting depth; drives the indent only (1 = the collection root's rows,
   *  one level under the collection's own row). */
  depth: number;
  /** Relative path of the open document, if any. */
  selectedPath: string | null;
  onSelect: (path: string) => void;
  /** What an EMPTY collection root says; nested levels say "nothing here". */
  emptyLabel?: string;
  /** This level is a collection's root, where Pages and Sources come first. */
  root?: boolean;
}

const indentOf = navIndent;

/** A collection root's own folders, in the order they come. */
const WIKI_FOLDERS = ["pages", "sources"] as const;

function rootRank(name: string): number {
  const i = (WIKI_FOLDERS as readonly string[]).indexOf(name);
  return i < 0 ? WIKI_FOLDERS.length : i;
}

export function KnowledgeTreeLevel({
  path,
  depth,
  selectedPath,
  onSelect,
  emptyLabel,
  root = false,
}: Props) {
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

  // A stable sort: the root's Pages and Sources first, the rest as listed.
  const directories = root
    ? [...data.directories].sort((a, b) => rootRank(a.name) - rootRank(b.name))
    : data.directories;
  const folderLabel = (name: string) =>
    root && rootRank(name) < WIKI_FOLDERS.length ? t(`knowledge.tree.${name}`) : name;
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
    <ul className="flex flex-col gap-px">
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
              <span className={NAV_CHEVRON}>
                {open ? (
                  <ChevronDown className="size-3" aria-hidden />
                ) : (
                  <ChevronRight className="size-3" aria-hidden />
                )}
              </span>
              {open ? (
                <FolderOpen className={NAV_ICON} aria-hidden />
              ) : (
                <Folder className={NAV_ICON} aria-hidden />
              )}
              <span className={NAV_FOLDER}>{folderLabel(dir.name)}</span>
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

      {data.files.map((file) => {
        const active = selectedPath === file.path;
        return (
          <li key={file.path}>
            <button
              type="button"
              onClick={() => onSelect(file.path)}
              aria-current={active ? "page" : undefined}
              title={file.title}
              style={indentOf(depth)}
              className={cn(NAV_ROW, active ? NAV_ROW_ACTIVE : NAV_ROW_IDLE)}
            >
              {/* The chevron's width, blank, so file rows line up with folders. */}
              <span className={NAV_CHEVRON} />
              <FileText className={NAV_ICON} aria-hidden />
              <span className={cn(NAV_NAME, active && "font-label")}>
                {file.path.split("/").pop()}
              </span>
              {file.kind === "source" && file.waiting ? (
                <span className="flex shrink-0 items-center gap-1 text-2xs text-text-muted">
                  <StatusDot tone="warn" size={6} />
                  {t("knowledge.waiting")}
                </span>
              ) : null}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
