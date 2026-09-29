// src/components/agents/tabs/AgentKindTab.tsx — the one layout of the agent's list tabs.
//
// Skills, MCP servers, Plugins and Hooks share it (board 2.1 "List tabs share
// one layout"): a one-line summary, the owner filter (All · Coffer's · the
// agent's own, kept in `?owner=`), a search box, the full table, an optional
// footnote, and one shared empty state naming the kind. Search and the owner
// filter narrow the rows here; the tab renders the table over what is left.
import { useMemo, useState, type ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { SearchInput } from "@/components/SearchInput";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import { filterByOwner, useOwnerFilter, type Owner } from "@/lib/agents/owner";
import { OwnerFilterControl } from "./OwnerFilterControl";

interface Props<R extends { owner: Owner }> {
  /** Every row, Coffer's and the agent's own. */
  rows: readonly R[];
  /** The one-line summary, e.g. "16 skills · 12 delivered by Coffer · 4 the agent's own". */
  summary: ReactNode;
  searchPlaceholder: string;
  /** The text a query is matched against, case-insensitively. */
  searchText: (row: R) => string;
  /** Renders the table over the rows left after the owner filter and search. */
  children: (visible: R[]) => ReactNode;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  /** Shown when the agent has no entry of this kind at all. */
  empty: { icon: LucideIcon; title: string; description: string };
  /** A muted line under the table (where the kind is managed, what an action does). */
  footnote?: ReactNode;
}

export function AgentKindTab<R extends { owner: Owner }>({
  rows,
  summary,
  searchPlaceholder,
  searchText,
  children,
  isLoading = false,
  error,
  onRetry,
  empty,
  footnote,
}: Props<R>) {
  const { t } = useTranslation();
  const [owner, setOwner] = useOwnerFilter();
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return filterByOwner(rows, owner).filter(
      (row) => !q || searchText(row).toLowerCase().includes(q),
    );
  }, [rows, owner, query, searchText]);

  if (error && rows.length === 0) {
    return (
      <EmptyState
        icon={empty.icon}
        tone="error"
        title={t("agents.kindTab.loadFailed")}
        description={translateApiError(t, error)}
        action={
          onRetry ? (
            <Button variant="outline" size="sm" onClick={onRetry}>
              {t("common.retry")}
            </Button>
          ) : undefined
        }
      />
    );
  }
  if (!isLoading && rows.length === 0) {
    return <EmptyState icon={empty.icon} title={empty.title} description={empty.description} />;
  }

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-text">{summary}</span>
        <span className="ml-auto inline-flex flex-wrap items-center gap-2.5">
          <OwnerFilterControl value={owner} onChange={setOwner} />
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder={searchPlaceholder}
            ariaLabel={searchPlaceholder}
            className="w-60"
          />
        </span>
      </div>
      {children(visible)}
      {footnote ? <p className="text-xs text-text-muted">{footnote}</p> : null}
    </div>
  );
}
