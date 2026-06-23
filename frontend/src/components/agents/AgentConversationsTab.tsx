// frontend/src/components/agents/AgentConversationsTab.tsx
// "Conversations" tab on the agent detail page: lists the agent's local
// transcript sessions (title, project, counts, start + last-activity times)
// through the shared DataTable so it matches every other resource surface —
// search box + page-based pagination + bulk select. The list is large and
// unbounded, so the table runs in DataTable's server-pagination mode: each page
// is fetched on demand (limit/offset) rather than loading every session up
// front. Per-row "distill to memory" (with inline insights) stays the primary
// action; "open in editor" / "reveal" fold into the row's "⋯" menu, and
// selecting rows enables a bulk distill. The project/time filters were dropped
// for parity with the other tables; the message-count / start / last-activity
// columns stay sortable (server-side sort + order), defaulting to most-recent
// activity first.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDown, ArrowUp } from "lucide-react";

import { AgentConversationsBulkActions } from "@/components/agents/AgentConversationsBulkActions";
import { DistillCell } from "@/components/agents/AgentConversationsDistillCell";
import { DistillStatus } from "@/components/agents/AgentConversationsStatus";
import { DataTable, type Column } from "@/components/DataTable";
import { RowActions } from "@/components/RowActions";
import { translateApiError } from "@/lib/api/errors";
import { useFileActionItems } from "@/lib/fileActionItems";
import type { SortOrder, TranscriptSessionSummary, TranscriptSort } from "@/lib/api/agentChat";
import { useDefaultPageSize } from "@/lib/preferences";
import { TRANSCRIPTS_PAGE_SIZE, useAgentTranscripts } from "@/lib/hooks/useAgentChatHistory";

function TimeCell({ value }: { value: string | null }) {
  return (
    <span className="text-xs text-muted-foreground">
      {value ? new Date(value).toLocaleString() : "—"}
    </span>
  );
}

/** Row actions: distill (primary, with inline insights) + open/reveal folded
 * into the "⋯" menu so the row never stacks three buttons. */
function ConversationRowActions({
  session,
  name,
}: {
  session: TranscriptSessionSummary;
  name: string;
}) {
  const { t } = useTranslation();
  const fileItems = useFileActionItems(session.source_path);
  return (
    <RowActions
      primary={<DistillCell session={session} name={name} />}
      items={fileItems}
      menuAriaLabel={t("common.moreActions")}
    />
  );
}

interface Props {
  /** Agent name — used as the route param for transcript queries. */
  name: string;
}

export function AgentConversationsTab({ name }: Props) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<TranscriptSort>("last_activity_at");
  const [order, setOrder] = useState<SortOrder>("desc");
  const defaultPageSize = useDefaultPageSize();
  const [pageSize, setPageSize] = useState(defaultPageSize || TRANSCRIPTS_PAGE_SIZE);

  const { data, isPending, error } = useAgentTranscripts(name, {
    q: search.trim() || undefined,
    sort,
    order,
    limit: pageSize,
    offset: (page - 1) * pageSize,
  });

  const rows = data?.sessions ?? [];
  const total = data?.total ?? 0;

  // Toggle direction when re-clicking the active column, else sort the new
  // column descending. Reset to page 1 so the new order starts from the top.
  const toggleSort = (col: TranscriptSort) => {
    if (sort === col) setOrder((o) => (o === "asc" ? "desc" : "asc"));
    else {
      setSort(col);
      setOrder("desc");
    }
    setPage(1);
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
      cell: (s) => (
        <span className="break-all font-mono text-xs">
          {s.project_path ?? <span className="text-muted-foreground">—</span>}
        </span>
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
    {
      key: "status",
      header: t("agents.conversationsTab.colStatus"),
      className: "whitespace-nowrap",
      cell: (s) => <DistillStatus status={s.distill_status} />,
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (s) => <ConversationRowActions session={s} name={name} />,
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
          search={{
            placeholder: t("agents.conversationsTab.searchPlaceholder"),
            value: search,
            onChange: setSearch,
          }}
          selection={{
            ariaSelectAll: t("common.bulk.selectAll"),
            ariaSelectRow: (s) => `${t("common.bulk.selectRow")}: ${s.title ?? s.session_id}`,
            bulkLabel: (count) => t("common.bulk.selected", { count }),
            clearLabel: t("common.clear"),
            renderBulkActions: ({ selectedRows, clear, allMatching }) => (
              <AgentConversationsBulkActions
                name={name}
                rows={selectedRows}
                onDone={clear}
                search={search}
                allMatching={allMatching}
              />
            ),
          }}
          serverPagination={{
            page,
            pageSize,
            total,
            onPageChange: setPage,
            onPageSizeChange: (s) => {
              setPageSize(s);
              setPage(1);
            },
          }}
          emptyMessage={t("agents.conversationsTab.empty")}
        />
      )}
    </div>
  );
}
