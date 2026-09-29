// frontend/src/components/agents/AgentConversationsTab.tsx
// "Conversations" tab on the agent detail page: a read-only browse surface over
// the agent's own local transcript sessions (title, project, counts, start +
// last-activity times) through the shared DataTable so it matches every other
// resource surface. The list is large and unbounded, so the table runs in
// DataTable's server-pagination mode: each page is fetched on demand (limit +
// the cursor the page before it returned) rather than loading every session up
// front — a cursor, not an offset, so a session the agent writes meanwhile does
// not shift the next page. Coffer never writes
// these files. Clicking a row opens that conversation's own page, which renders
// the .jsonl as a readable dialogue and carries the open-in-editor / reveal
// actions; the table itself offers no per-row menu, because a list of a thousand
// sessions is for finding one, and everything you can do to the one you found
// belongs where you can see it. The message-count / start / last-activity
// columns are sortable (server-side sort + order), defaulting to most-recent
// activity first.
//
// The search box is debounced HERE rather than inside DataTable: every other
// DataTable caller filters rows it already holds, where a delay would only make
// typing feel slower, and this is the one surface where a keystroke can cost a
// full transcript parse on a cold reader. The input itself stays instant — only
// the value that becomes a query key waits.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowDown, ArrowUp } from "lucide-react";

import { DataTable, type Column } from "@/components/DataTable";
import { translateApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/utils";
import type {
  SortOrder,
  TranscriptSessionSummary,
  TranscriptSort,
} from "@/lib/api/agentTranscripts";
import { useDefaultPageSize } from "@/lib/preferences";
import { useDebouncedValue } from "@/lib/hooks/useDebouncedValue";
import { TRANSCRIPTS_PAGE_SIZE, useAgentTranscripts } from "@/lib/hooks/useAgentTranscripts";

function TimeCell({ value }: { value: string | null }) {
  const { t } = useTranslation();
  return (
    <span className="text-xs text-muted-foreground">
      {value ? formatDateTime(value) : t("common.emptyValue")}
    </span>
  );
}

interface Props {
  /** The agent's uid — the route param every transcript query is addressed
   *  by, and what this tab's own sub-page links are built from. */
  uid: string;
}

export function AgentConversationsTab({ uid }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  // cursors[p - 1] reads page p; page 1 needs none. Paging is prev/next only,
  // so every page reached has its cursor recorded by the page before it.
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const [sort, setSort] = useState<TranscriptSort>("last_activity_at");
  const [order, setOrder] = useState<SortOrder>("desc");
  const defaultPageSize = useDefaultPageSize();
  const [pageSize, setPageSize] = useState(defaultPageSize || TRANSCRIPTS_PAGE_SIZE);

  const debouncedSearch = useDebouncedValue(search);

  const { data, isPending, isPlaceholderData, error } = useAgentTranscripts(uid, {
    q: debouncedSearch.trim() || undefined,
    sort,
    order,
    limit: pageSize,
    cursor: cursors[page - 1],
  });

  const rows = data?.sessions ?? [];
  const total = data?.total ?? 0;
  // Record the cursor this page hands the next one — but not from the previous
  // page's answer still on screen while this one loads.
  const nextCursor = isPlaceholderData ? undefined : (data?.next_cursor ?? undefined);
  if (nextCursor && cursors[page] !== nextCursor) {
    setCursors((cs) => [...cs.slice(0, page), nextCursor]);
  }

  // Back to page 1 whenever the query changes: a cursor is bound to the search
  // and sort it was issued for.
  const firstPage = () => {
    setPage(1);
    setCursors([undefined]);
  };
  const goToPage = (p: number) => {
    if (p === 1 || cursors[p - 1]) setPage(p);
  };

  // Toggle direction when re-clicking the active column, else sort the new
  // column descending. Reset to page 1 so the new order starts from the top.
  const toggleSort = (col: TranscriptSort) => {
    if (sort === col) setOrder((o) => (o === "asc" ? "desc" : "asc"));
    else {
      setSort(col);
      setOrder("desc");
    }
    firstPage();
  };

  const sortHeader = (col: TranscriptSort, label: string) => (
    <button
      type="button"
      className="inline-flex items-center gap-1 hover:text-foreground"
      onClick={() => toggleSort(col)}
      aria-label={t("agents.conversationsTab.sortBy", { field: label })}
    >
      {label}
      {sort === col ? (
        order === "asc" ? (
          <ArrowUp className="size-3" aria-hidden />
        ) : (
          <ArrowDown className="size-3" aria-hidden />
        )
      ) : null}
    </button>
  );

  const columns: Column<TranscriptSessionSummary>[] = [
    {
      key: "title",
      header: t("agents.conversationsTab.colTitle"),
      className: "max-w-md",
      cell: (s) => (
        <span className="line-clamp-2 text-sm">
          {s.title ?? <span className="text-muted-foreground">—</span>}
        </span>
      ),
    },
    {
      key: "project",
      header: t("agents.conversationsTab.colProject"),
      cell: (s) =>
        s.project_path ? (
          <span
            className="line-clamp-1 max-w-xs break-all font-mono text-xs text-muted-foreground"
            title={s.project_path}
          >
            {s.project_path}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "messages",
      header: sortHeader("message_count", t("agents.conversationsTab.colMessages")),
      className: "whitespace-nowrap text-right",
      cell: (s) => <span className="text-sm tabular-nums">{s.message_count}</span>,
    },
    {
      key: "started",
      header: sortHeader("started_at", t("agents.conversationsTab.colStarted")),
      className: "whitespace-nowrap",
      cell: (s) => <TimeCell value={s.started_at} />,
    },
    {
      key: "lastActivity",
      header: sortHeader("last_activity_at", t("agents.conversationsTab.colLastActivity")),
      className: "whitespace-nowrap",
      cell: (s) => <TimeCell value={s.last_activity_at} />,
    },
  ];

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <h3 className="text-sm font-medium text-muted-foreground">
          {t("agents.conversationsTab.title")}
        </h3>
        <p className="text-xs text-muted-foreground">{t("agents.conversationsTab.subtitle")}</p>
      </div>

      {isPending ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : error ? (
        <p className="text-sm text-destructive">{translateApiError(t, error)}</p>
      ) : (
        <DataTable
          rows={rows}
          columns={columns}
          // Key by the transcript file: one session_id can span several files
          // (subagent sidechains), so session_id is NOT unique per row.
          rowKey={(s) => s.source_path}
          // The session is addressed by its FILE, here as in the key above:
          // one session_id can span several files (subagent sidechains), so a
          // page keyed by session_id would sometimes open the wrong one.
          onRowClick={(s) =>
            navigate(
              `/agents/${encodeURIComponent(uid)}/conversations?${new URLSearchParams({
                path: s.source_path,
              })}`,
            )
          }
          search={{
            placeholder: t("agents.conversationsTab.searchPlaceholder"),
            value: search,
            // Back to page 1 on every new query: the old cursor was issued for
            // the previous search and would be refused.
            onChange: (v) => {
              setSearch(v);
              firstPage();
            },
          }}
          serverPagination={{
            page,
            pageSize,
            total,
            onPageChange: goToPage,
            onPageSizeChange: (s) => {
              setPageSize(s);
              firstPage();
            },
          }}
          emptyMessage={t("agents.conversationsTab.empty")}
        />
      )}
    </div>
  );
}
