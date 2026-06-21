// frontend/src/components/agents/AgentConversationsTab.tsx
// "Conversations" tab on the agent detail page: lists the agent's local
// transcript sessions (title, project, counts, start + last-activity times)
// with server-side search / project + time filters / sortable columns and a
// "load more" pager, plus per-row "reveal the session file" and "distill to
// memory" actions.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDown, ArrowUp } from "lucide-react";

import { DistillCell } from "@/components/agents/AgentConversationsDistillCell";
import { AgentConversationsToolbar } from "@/components/agents/AgentConversationsToolbar";
import { Button } from "@/components/ui/button";
import { FileActions } from "@/components/FileActions";
import { type TimeRangeValue } from "@/components/TimeRangePicker";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { translateApiError } from "@/lib/api/errors";
import { resolveTimeWindow } from "@/lib/timeRange";
import type { SortOrder, TranscriptSort } from "@/lib/api/agentChat";
import { useAgentTranscripts, type TranscriptFilters } from "@/lib/hooks/useAgentChatHistory";

function TimeCell({ value }: { value: string | null }) {
  return (
    <span className="text-xs text-muted-foreground">
      {value ? new Date(value).toLocaleString() : "—"}
    </span>
  );
}

interface Props {
  /** Agent name — used as the route param for transcript queries. */
  name: string;
}

export function AgentConversationsTab({ name }: Props) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [project, setProject] = useState("all");
  const [time, setTime] = useState<TimeRangeValue>({ timeRange: "all", from: "", to: "" });
  const [sort, setSort] = useState<TranscriptSort>("last_activity_at");
  const [order, setOrder] = useState<SortOrder>("desc");

  const window = resolveTimeWindow(time);
  const filters: TranscriptFilters = {
    q: search.trim() || undefined,
    project: project !== "all" ? project : undefined,
    startedAfter: window.since,
    startedBefore: window.until,
    sort,
    order,
  };

  const { data, isPending, error, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useAgentTranscripts(name, filters);

  const rows = useMemo(() => data?.pages.flatMap((p) => p.sessions) ?? [], [data]);
  const total = data?.pages[0]?.total ?? 0;

  // Project filter options derive from the loaded rows' distinct paths (plus the
  // current selection so it never disappears mid-filter).
  const projectOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of rows) if (r.project_path) set.add(r.project_path);
    if (project !== "all") set.add(project);
    return [...set].sort();
  }, [rows, project]);

  const toggleSort = (key: TranscriptSort) => {
    if (sort === key) {
      setOrder((o) => (o === "asc" ? "desc" : "asc"));
    } else {
      setSort(key);
      setOrder("desc");
    }
  };

  function SortHeader({
    col,
    label,
    className,
  }: {
    col: TranscriptSort;
    label: string;
    className?: string;
  }) {
    return (
      <TableHead className={className}>
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
      </TableHead>
    );
  }

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
        <>
          <AgentConversationsToolbar
            search={search}
            onSearchChange={setSearch}
            project={project}
            onProjectChange={setProject}
            projectOptions={projectOptions}
            time={time}
            onTimeChange={setTime}
          />

          <div className="rounded-md border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("agents.conversationsTab.colTitle")}</TableHead>
                  <TableHead>{t("agents.conversationsTab.colProject")}</TableHead>
                  <SortHeader
                    col="message_count"
                    label={t("agents.conversationsTab.colMessages")}
                    className="whitespace-nowrap text-right"
                  />
                  <SortHeader
                    col="started_at"
                    label={t("agents.conversationsTab.colStarted")}
                    className="whitespace-nowrap"
                  />
                  <SortHeader
                    col="last_activity_at"
                    label={t("agents.conversationsTab.colLastActivity")}
                    className="whitespace-nowrap"
                  />
                  <TableHead className="text-right" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.length === 0 ? (
                  <TableRow className="hover:bg-transparent">
                    <TableCell colSpan={6} className="py-10 text-center text-muted-foreground">
                      {t("agents.conversationsTab.empty")}
                    </TableCell>
                  </TableRow>
                ) : (
                  rows.map((s) => (
                    <TableRow key={s.session_id}>
                      <TableCell className="max-w-md py-3">
                        <span className="line-clamp-2 text-sm">
                          {s.title ?? <span className="text-muted-foreground">—</span>}
                        </span>
                      </TableCell>
                      <TableCell className="py-3">
                        <span className="break-all font-mono text-xs">
                          {s.project_path ?? <span className="text-muted-foreground">—</span>}
                        </span>
                      </TableCell>
                      <TableCell className="whitespace-nowrap py-3 text-right">
                        <span className="text-sm tabular-nums">{s.message_count}</span>
                      </TableCell>
                      <TableCell className="whitespace-nowrap py-3">
                        <TimeCell value={s.started_at} />
                      </TableCell>
                      <TableCell className="whitespace-nowrap py-3">
                        <TimeCell value={s.last_activity_at} />
                      </TableCell>
                      <TableCell className="py-3 text-right">
                        <div className="flex flex-col items-end gap-2">
                          <FileActions filePath={s.source_path} />
                          <DistillCell session={s} name={name} />
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-muted-foreground">
              {t("agents.conversationsTab.showingCount", { count: rows.length, total })}
            </p>
            {hasNextPage ? (
              <Button
                size="sm"
                variant="outline"
                disabled={isFetchingNextPage}
                onClick={() => void fetchNextPage()}
              >
                {isFetchingNextPage ? t("common.loading") : t("agents.conversationsTab.loadMore")}
              </Button>
            ) : null}
          </div>
        </>
      )}
    </div>
  );
}
