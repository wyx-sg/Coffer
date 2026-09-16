// frontend/src/pages/sync/SyncRunsTab.tsx — Sync → Runs.
//
// Every converge round this machine has run, newest first (spec vault-sync
// `## The converge round`), and the whole of what Sync has to say about itself.
//
// There used to be a Status tab beside this one, carrying two banners: a
// conflict, and a round the deletion guard held. Both are gone, because
// neither was a state BESIDE the history — each is the newest row OF it. A
// held round is a round; splitting "what is waiting" from "what has happened"
// made one situation readable in two places and actionable in only one.
//
// The shared DataTable, so search, the status filter and paging come for free
// and this does not become a bespoke table. The whole window arrives in one
// request and is filtered in the browser, exactly as the Activity page's tabs
// do, because 500 rounds is a small payload and a server round-trip per
// keystroke is not worth it.
//
// Rounds that changed nothing are FOLDED rather than listed or dropped — see
// `syncRunRows.ts` for why both alternatives are worse. They were the majority
// (14 of 27 here), and one row each buried everything that mattered; but they
// are also the only evidence that a vault which stopped converging on Tuesday
// is not simply a vault with nothing to do, so a fold that states its span
// keeps what a filter would have thrown away.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { Card, CardContent } from "@/components/ui/card";
import { DataTable, type FilterDef } from "@/components/DataTable";
import { translateApiError } from "@/lib/api/errors";
import { useSyncRuns, useSyncStatus } from "@/lib/hooks/useSync";
import type { RunRecord } from "@/lib/api/sync";
import { formatDateTime } from "@/lib/utils";
import { SyncConflictBanner } from "./SyncConflictBanner";
import { SyncRunDetail } from "./SyncRunDetail";
import { rowSearchHaystack, rowStatus, statusLabel, syncRunColumns } from "./syncRunColumns";
import {
  collapseQuietRounds,
  heldRoundId,
  quietSpan,
  rollbackTargetId,
  type SyncRunRow,
} from "./syncRunRows";

/** The statuses a round can end in — the filter's options, in severity order. */
const STATUSES = [
  "ok",
  "no_change",
  "conflict",
  "awaiting_confirmation",
  "push_failed",
  "failed",
  "disabled",
] as const;

interface Props {
  /** False while another tab is in front: no request, no discarded response. */
  enabled: boolean;
}


/** A folded row opened up: which rounds it stands in for. */
function QuietDetail({ runs }: { runs: RunRecord[] }) {
  const { t } = useTranslation();
  const span = quietSpan(runs);
  return (
    <div className="space-y-2 px-4 py-3">
      <p className="text-sm text-muted-foreground">
        {t("sync.runs.quietDetail", {
          count: span.count,
          from: formatDateTime(span.from),
          to: formatDateTime(span.to),
        })}
      </p>
      {/* The individual finish times, and nothing else: a quiet round has no
          other field worth a line, and listing five empty tallies would say
          less than the count above already does. */}
      <ul className="space-y-0.5 font-mono text-xs text-muted-foreground">
        {runs.map((run) => (
          <li key={run.id}>{formatDateTime(run.finished_at)}</li>
        ))}
      </ul>
    </div>
  );
}

export function SyncRunsTab({ enabled }: Props) {
  const { t } = useTranslation();
  // isLoading, not isPending: a disabled query stays "pending" forever, which
  // would leave a tab that has never been opened stuck on the loading card the
  // moment it is.
  const { data, isLoading, error } = useSyncRuns(enabled);
  // The vault's CURRENT pending state, which the history cannot answer on its
  // own: several rows keep `awaiting_confirmation` as their outcome after the
  // situation was answered, because answering raises a further round rather
  // than rewriting the ones that were held.
  const status = useSyncStatus();
  const runs = useMemo(() => data?.runs ?? [], [data]);
  const rows = useMemo(() => collapseQuietRounds(runs), [runs]);
  // Which row may offer "Undo this round": `POST /sync/rollback` names no
  // round, it reverses the newest pre-apply snapshot, so exactly one row can
  // honestly carry the action. Computed over the WHOLE history rather than the
  // visible page — a filter that hides the newest round must not promote the
  // one under it into a target it is not.
  const rollbackTarget = useMemo(() => rollbackTargetId(runs), [runs]);
  const heldTarget = useMemo(
    () => heldRoundId(runs, Boolean(status.data?.last_run?.pending)),
    [runs, status.data],
  );
  const conflicts = status.data?.last_run?.conflicts ?? [];

  const filters: FilterDef<SyncRunRow>[] = [
    {
      key: "status",
      label: t("sync.history.filter.outcome"),
      allLabel: t("resources.status.all"),
      accessor: rowStatus,
      options: STATUSES.map((s) => ({ value: s, label: statusLabel(t, s) })),
    },
  ];

  if (isLoading) {
    return (
      <Card className="paper-card">
        <CardContent className="py-10 text-center text-muted-foreground">
          {t("common.loading")}
        </CardContent>
      </Card>
    );
  }

  // An error renders inside this tab — a daemon too old to serve /sync/runs
  // 404s, and that must not blank the two tabs it does still serve.
  if (error) {
    return (
      <Card className="paper-card border-destructive/40">
        <CardContent className="py-4 text-destructive">{translateApiError(t, error)}</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* The one thing that is genuinely not a row: a conflict names paths the
          user has to go and resolve with their own git, in a working tree the
          table has no column for. It stays a banner, above the round it
          belongs to. */}
      {conflicts.length > 0 ? (
        <SyncConflictBanner
          paths={conflicts}
          worktree={status.data?.remote?.worktree_path ?? null}
        />
      ) : null}
      <p className="text-sm text-muted-foreground">{t("sync.history.description")}</p>
      {/* No re-sort: the daemon returns the rounds newest-first, the fold
          preserves that order, and DataTable preserves the order it is handed. */}
      <DataTable
        rows={rows}
        columns={syncRunColumns(t, { rollbackTarget, heldTarget })}
        rowKey={(row) => row.id}
        search={{
          accessor: (row) => rowSearchHaystack(t, row),
          placeholder: t("sync.history.searchPlaceholder"),
        }}
        filters={filters}
        getRowDetail={(row) =>
          row.kind === "run" ? <SyncRunDetail run={row.run} /> : <QuietDetail runs={row.runs} />
        }
        emptyMessage={t("sync.history.empty")}
      />
    </div>
  );
}
