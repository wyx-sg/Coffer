// frontend/src/components/memory/MemoryScopeList.tsx
//
// The Memory page's list pane (spec memory "Manage memory sync in the web UI
// and on the command line"): global memories first — written into every agent
// on every machine — then the hub's projects, each by its short name with how
// many memories it holds. A project not checked out on this machine is dimmed:
// its memories wait in the hub. A row opens its memories beside the list
// (`?scope=`); the full project key is the row's tooltip.
import { useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FolderGit2, Globe } from "lucide-react";

import { ListLoadingRows } from "@/components/ListPaneStates";
import { SearchInput } from "@/components/SearchInput";
import { NAV_ICON, NAV_ROW_ACTIVE, NAV_ROW_IDLE } from "@/components/knowledge/navRow";
import type { SyncProject } from "@/lib/api/memoryTypes";
import { GLOBAL_SCOPE, projectName } from "@/lib/memory/syncFacts";
import { cn } from "@/lib/utils";

/** More projects than this and a search appears. */
const SEARCH_FROM = 8;

interface Props {
  projects: readonly SyncProject[];
  globalMemories: number;
  /** The open scope: `global` or a project's hub folder. */
  selected: string | null;
  isLoading?: boolean;
}

function ScopeRow({
  to,
  current,
  icon: Icon,
  name,
  title,
  count,
  dimmed = false,
}: {
  to: string;
  current: boolean;
  icon: typeof Globe;
  name: string;
  title?: string;
  count: number;
  dimmed?: boolean;
}) {
  return (
    <li>
      <Link
        to={to}
        title={title}
        aria-current={current ? "page" : undefined}
        className={cn(
          "flex h-8 w-full min-w-0 items-center gap-2 rounded-item px-2.5 text-left text-sm text-text transition-colors",
          current ? NAV_ROW_ACTIVE : NAV_ROW_IDLE,
          dimmed && "text-text-muted",
        )}
      >
        <Icon className={NAV_ICON} aria-hidden />
        <span className="min-w-0 flex-1 truncate">{name}</span>
        <span className="shrink-0 text-xs tabular-nums text-text-muted">{count}</span>
      </Link>
    </li>
  );
}

export function MemoryScopeList({ projects, globalMemories, selected, isLoading = false }: Props) {
  const { t } = useTranslation();
  const { search } = useLocation();
  const [query, setQuery] = useState("");
  const to = (scope: string) => {
    const params = new URLSearchParams(search);
    params.set("scope", scope);
    params.delete("memory");
    return `/memory?${params.toString()}`;
  };
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? projects.filter((p) => p.key.toLowerCase().includes(q)) : projects;
  }, [projects, query]);
  const here = shown.filter((p) => p.checked_out);
  const elsewhere = shown.filter((p) => !p.checked_out);

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
          <>
            <ul className="mb-3 flex flex-col gap-0.5">
              <ScopeRow
                to={to(GLOBAL_SCOPE)}
                current={selected === GLOBAL_SCOPE}
                icon={Globe}
                name={t("memory.projects.global")}
                count={globalMemories}
              />
            </ul>
            {[
              ["here", here],
              ["elsewhere", elsewhere],
            ].map(([group, rows]) =>
              (rows as SyncProject[]).length === 0 ? null : (
                <section key={group as string} className="mb-3">
                  <h2 className="px-2.5 pb-1 text-2xs font-semibold text-text-muted">
                    {t(`memory.scopes.${group as string}`)}
                  </h2>
                  <ul className="flex flex-col gap-0.5">
                    {(rows as SyncProject[]).map((p) => (
                      <ScopeRow
                        key={p.key}
                        to={to(p.folder)}
                        current={selected === p.folder}
                        icon={FolderGit2}
                        name={projectName(p.key)}
                        title={p.key}
                        count={p.memories}
                        dimmed={!p.checked_out}
                      />
                    ))}
                  </ul>
                </section>
              ),
            )}
          </>
        )}
      </nav>
    </div>
  );
}
