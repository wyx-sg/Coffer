// frontend/src/components/knowledge/KnowledgeTreeLevel.tsx
//
// ONE level of a collection's tree, and the recursion that walks it. The
// rows are deliberately the same rows the skill Files tab draws
// (`SkillFileTree`): chevron, folder / open-folder or file icon, one truncated
// line, a depth-proportional indent instead of a rail, and the selected file
// filled `bg-surface-selected`. Two file browsers that behave the same should look
// the same, so a reader who has opened one has already learned the other.
//
// What is NOT copied is the fetch. A skill's whole folder arrives in a single
// response, so that tree can afford to open its first two levels on mount. A
// collection descends a level per request, so each expanded directory
// mounts another level and fetches its own listing — and directories therefore
// start CLOSED: pre-opening them would fire one request per child folder for a
// subtree nobody has asked to see.
//
// One hidden entry is listed: a collection's `.inbox`, first at the root while
// it holds material waiting to be merged (spec knowledge "Present a collection
// as one tree in the web UI"). Its row says what it is — an inbox icon, a
// plain-language label and how many items wait — rather than a bare dot-name,
// and it expands like any folder. The items inside carry `inbox: true`; they
// open in the viewer read-only, so their rows are drawn muted.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen, Inbox } from "lucide-react";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useKnowledgeTree } from "@/lib/hooks/useKnowledge";

interface Props {
  /** Directory to list, relative to the knowledge root (`shopee` for the
   *  collection itself, `shopee/account` for a folder inside it). */
  path: string;
  /** Nesting depth; drives the indent only (0 = the collection root). */
  depth: number;
  /** Relative path of the file being previewed, if it is at this level. */
  selectedPath: string | null;
  onSelect: (path: string) => void;
  /** What an EMPTY collection root says — how to put the first document in,
   *  which an empty subfolder has no need to repeat. The caller passes it for
   *  the root only; nested levels fall back to a plain "nothing here". */
  emptyLabel?: string;
}

/** Row indent, matching `SkillFileTree`'s: 0.75rem a level, 0.25rem of gutter. */
function indentOf(depth: number): { paddingLeft: string } {
  return { paddingLeft: `${depth * 0.75 + 0.25}rem` };
}

export function KnowledgeTreeLevel({ path, depth, selectedPath, onSelect, emptyLabel }: Props) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<string[]>([]);
  const { data, isPending, error } = useKnowledgeTree(path);

  if (error) {
    return (
      <p style={indentOf(depth)} className="py-1.5 text-sm text-destructive" role="alert">
        {translateApiError(t, error)}
      </p>
    );
  }
  if (isPending) {
    // Skeleton rows rather than the word "Loading": the column keeps the shape
    // it is about to have, so the pane beside it does not jump (§6).
    return (
      <div style={indentOf(depth)} className="space-y-2 py-1.5" aria-busy>
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  }

  const files = data.files;
  if (data.directories.length === 0 && files.length === 0) {
    return (
      <p style={indentOf(depth)} className="py-1.5 text-sm text-muted-foreground">
        {emptyLabel ?? t("knowledge.detail.emptyFolder")}
      </p>
    );
  }

  const toggle = (dirPath: string) =>
    setExpanded((open) =>
      open.includes(dirPath) ? open.filter((p) => p !== dirPath) : [...open, dirPath],
    );

  return (
    <ul className="space-y-0.5">
      {data.directories.map((dir) => {
        const open = expanded.includes(dir.path);
        return (
          <li key={dir.path}>
            <button
              type="button"
              onClick={() => toggle(dir.path)}
              aria-expanded={open}
              style={indentOf(depth)}
              className="flex w-full items-center gap-1.5 rounded-md py-1.5 pr-2 text-left text-sm transition-colors hover:bg-surface-hover hover:text-text"
            >
              {open ? (
                <ChevronDown className="size-3.5 shrink-0 opacity-70" />
              ) : (
                <ChevronRight className="size-3.5 shrink-0 opacity-70" />
              )}
              {dir.inbox ? (
                <Inbox className="size-4 shrink-0 opacity-70" />
              ) : open ? (
                <FolderOpen className="size-4 shrink-0 opacity-70" />
              ) : (
                <Folder className="size-4 shrink-0 opacity-70" />
              )}
              {dir.inbox ? (
                <>
                  <span className="truncate">{t("knowledge.detail.inboxFolder")}</span>
                  <span className="ml-auto shrink-0 text-xs tabular-nums text-muted-foreground">
                    {dir.file_count}
                  </span>
                </>
              ) : (
                <span className="truncate">{dir.name}</span>
              )}
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

      {files.map((file) => (
        <li key={file.path}>
          <button
            type="button"
            onClick={() => onSelect(file.path)}
            style={indentOf(depth)}
            className={cn(
              "flex w-full items-center gap-1.5 rounded-md py-1.5 pr-2 text-left text-sm transition-colors",
              selectedPath === file.path
                ? "bg-surface-selected text-text"
                : "hover:bg-surface-hover hover:text-text",
              file.inbox && selectedPath !== file.path && "text-muted-foreground",
            )}
          >
            {/* The chevron's width, kept as blank space so file rows line up
                with the folder rows beside them — `SkillFileTree` does the
                same. */}
            <span className="size-3.5 shrink-0" />
            <FileText className="size-4 shrink-0 opacity-70" />
            {/* The frontmatter title, not the slug: it is what the file calls
                itself, and the slug is on the viewer's path line anyway. */}
            <span className="truncate">{file.title}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
