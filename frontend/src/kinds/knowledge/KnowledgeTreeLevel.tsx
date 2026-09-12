// frontend/src/kinds/knowledge/KnowledgeTreeLevel.tsx
//
// ONE level of the knowledge catalogue, and the recursion that walks it. Each
// expanded directory mounts another level, which fetches its own listing — the
// catalogue descends a level per request (FR-021), so nothing loads a subtree
// the user has not opened.
//
// The filter narrows FILES only. A directory's children are not loaded until it
// is expanded, so hiding a directory whose name doesn't match would hide
// matches the user cannot see yet; directories therefore always stay visible.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, FileText, Folder } from "lucide-react";

import { cn } from "@/lib/utils";
import { translateApiError } from "@/lib/api/errors";
import { matchesFilter } from "./filter";
import { useKnowledgeTree } from "./useKnowledge";

interface Props {
  /** Directory to list, relative to the knowledge root (`shopee/account`). */
  path: string;
  /** Nesting depth; drives the indent rail only (0 = the collection root). */
  depth: number;
  /** Relative path of the file being previewed, if it is at this level. */
  selectedPath: string | null;
  /** Client-side filename filter, applied to this level's files. */
  filter: string;
  onSelect: (path: string) => void;
}

export function KnowledgeTreeLevel({ path, depth, selectedPath, filter, onSelect }: Props) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<string[]>([]);
  const { data, isPending, error } = useKnowledgeTree(path);

  if (error) {
    return (
      <p className="px-1 text-sm text-destructive" role="alert">
        {translateApiError(t, error)}
      </p>
    );
  }
  if (isPending) {
    return <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>;
  }

  const files = data.files.filter((f) => matchesFilter(filter, f.title, f.path));
  if (data.directories.length === 0 && files.length === 0) {
    return (
      <p className="px-1 text-sm text-muted-foreground">
        {filter.trim() ? t("knowledge.detail.noMatches") : t("knowledge.detail.emptyFolder")}
      </p>
    );
  }

  const toggle = (dirPath: string) =>
    setExpanded((open) =>
      open.includes(dirPath) ? open.filter((p) => p !== dirPath) : [...open, dirPath],
    );

  return (
    <ul className={cn("space-y-0.5", depth > 0 && "ml-2 border-l border-border/60 pl-2")}>
      {data.directories.map((dir) => {
        const open = expanded.includes(dir.path);
        return (
          <li key={dir.path}>
            <button
              type="button"
              onClick={() => toggle(dir.path)}
              aria-expanded={open}
              className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-secondary hover:text-foreground"
            >
              {open ? (
                <ChevronDown className="size-3.5 shrink-0 opacity-70" />
              ) : (
                <ChevronRight className="size-3.5 shrink-0 opacity-70" />
              )}
              <Folder className="size-4 shrink-0 opacity-70" />
              <span className="min-w-0 flex-1 truncate">{dir.name}</span>
              <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                {dir.file_count}
              </span>
            </button>
            {open ? (
              <KnowledgeTreeLevel
                path={dir.path}
                depth={depth + 1}
                selectedPath={selectedPath}
                filter={filter}
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
            className={cn(
              "flex w-full items-start gap-1.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
              selectedPath === file.path
                ? "bg-primary/10 text-primary"
                : "hover:bg-secondary hover:text-foreground",
            )}
          >
            <FileText className="mt-0.5 size-4 shrink-0 opacity-70" />
            <span className="min-w-0 flex-1">
              <span className="block truncate">{file.title}</span>
              {file.description ? (
                <span className="block truncate text-xs text-muted-foreground">
                  {file.description}
                </span>
              ) : null}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
