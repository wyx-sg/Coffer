// src/components/agents/tabs/AgentKindTab.tsx — the search-and-list region of an agent's list tabs.
//
// Skills, MCP servers and Plugins share it (boards 2.1.20, 2.1.25, 2.1.31,
// shared empty 2.1.55): a search box (with an optional "?" beside it), an
// optional notice between the search and the list, then one bordered list of
// hairline rows the tab renders. A kind with nothing in it shows the same
// bordered box with a 13/600 title and one line, no icon, and keeps the search;
// a list that failed to load is the shared load-error row.
import { useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { LoadErrorRow } from "@/components/LoadErrorRow";
import { SearchInput } from "@/components/SearchInput";
import { Skeleton } from "@/components/ui/skeleton";
import { TabEmpty } from "./TabEmpty";

interface Props<R> {
  rows: readonly R[];
  searchPlaceholder: string;
  /** The text a query is matched against, case-insensitively. */
  searchText: (row: R) => string;
  /** One `<li>` per visible row; the bordered `<ul>` around them is drawn here. */
  children: (visible: R[]) => ReactNode;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  /** Shown in the bordered box when the kind holds nothing at all. */
  empty: { title: string; description: string };
  /** Sits right of the search box, e.g. a "?" HelpTip. */
  searchAside?: ReactNode;
  /** Between the search box and the list: a parse error, a missing program. */
  notice?: ReactNode;
  noMatch: string;
}

/** The frame every list of rows shares (Memory, Skills, MCP servers, Plugins). */
const LIST_FRAME = "overflow-hidden rounded-lg border border-border bg-surface-raised";

export function AgentKindTab<R>({
  rows,
  searchPlaceholder,
  searchText,
  children,
  isLoading = false,
  error,
  onRetry,
  empty,
  searchAside,
  notice,
  noMatch,
}: Props<R>) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((row) => !q || searchText(row).toLowerCase().includes(q));
  }, [rows, query, searchText]);

  let body: ReactNode;
  if (error && rows.length === 0) {
    body = <LoadErrorRow title={t("agents.kindTab.loadFailed")} error={error} onRetry={onRetry} />;
  } else if (isLoading && rows.length === 0) {
    body = <Skeleton className="h-28 w-full" aria-busy="true" />;
  } else if (rows.length === 0) {
    body = <TabEmpty title={empty.title} description={empty.description} />;
  } else if (visible.length === 0) {
    body = <p className="py-4 text-sm text-text-muted">{noMatch}</p>;
  } else {
    body = <ul className={LIST_FRAME}>{children(visible)}</ul>;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder={searchPlaceholder}
          ariaLabel={searchPlaceholder}
          className="w-60"
        />
        {searchAside}
      </div>
      {notice}
      {body}
    </div>
  );
}
