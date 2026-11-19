// frontend/src/components/memory/MemoryScopeList.tsx
//
// The Memory page's list pane (spec memory "Show and edit memory on the Memory
// page"): one row per project folder in the hub, with how many topic files it
// holds and a warning when some break the format. A row opens its topics beside
// the list (`?scope=`).
import { useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertTriangle, FolderGit2 } from "lucide-react";

import { ListLoadingRows } from "@/components/ListPaneStates";
import { SearchInput } from "@/components/SearchInput";
import { NAV_ICON, NAV_ROW_ACTIVE, NAV_ROW_IDLE } from "@/components/knowledge/navRow";
import type { MemoryProject } from "@/lib/api/memoryTypes";
import { projectName } from "@/lib/memory/projects";
import { cn } from "@/lib/utils";

/** More projects than this and a search appears. */
const SEARCH_FROM = 8;

interface Props {
  projects: readonly MemoryProject[];
  /** The open project's folder. */
  selected: string | null;
  isLoading?: boolean;
}

export function MemoryScopeList({ projects, selected, isLoading = false }: Props) {
  const { t } = useTranslation();
  const { search } = useLocation();
  const [query, setQuery] = useState("");
  const to = (folder: string) => {
    const params = new URLSearchParams(search);
    params.set("scope", folder);
    params.delete("file");
    params.delete("history");
    return `/memory?${params.toString()}`;
  };
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? projects.filter((p) => p.folder.toLowerCase().includes(q)) : projects;
  }, [projects, query]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {projects.length > SEARCH_FROM ? (
        <div className="px-3 pb-2.5 pt-3.5">
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder={t("memory.scopes.search")}
            ariaLabel={t("memory.scopes.search")}
          />
        </div>
      ) : null}
      <nav
        aria-label={t("memory.scopes.label")}
        className="min-h-0 flex-1 overflow-y-auto px-2 pb-3 pt-3"
      >
        {isLoading ? (
          <ListLoadingRows />
        ) : (
          <ul className="flex flex-col gap-0.5">
            {shown.map((p) => (
              <li key={p.folder}>
                <Link
                  to={to(p.folder)}
                  title={p.folder}
                  aria-current={selected === p.folder ? "page" : undefined}
                  className={cn(
                    "flex h-8 w-full min-w-0 items-center gap-2 rounded-item px-2.5 text-left text-sm text-text transition-colors",
                    selected === p.folder ? NAV_ROW_ACTIVE : NAV_ROW_IDLE,
                  )}
                >
                  <FolderGit2 className={NAV_ICON} aria-hidden />
                  <span className="min-w-0 flex-1 truncate">{projectName(p.folder)}</span>
                  {p.problems > 0 ? (
                    <AlertTriangle
                      className="size-3.5 shrink-0 text-warning"
                      aria-label={t("memory.scopes.problems", { count: p.problems })}
                    />
                  ) : null}
                  <span className="shrink-0 text-xs tabular-nums text-text-muted">{p.topics}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </nav>
    </div>
  );
}
