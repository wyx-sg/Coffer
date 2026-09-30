// frontend/src/pages/sync/SyncRunsTab.tsx — Sync → Runs.
//
// What a person opens Sync to find out, top to bottom: whether it is working
// (`SyncStatusSection` — the status, anything wrong, anything a stopped round
// or a join is waiting on, and what is waiting to push), then every round this
// machine has run, newest first.
//
// The shared DataTable, so search, the status filter and paging come for free.
// The whole window arrives in one request and is filtered in the browser,
// because 500 rounds is a small payload and a round-trip per keystroke is not
// worth it. Rounds that repeated one outcome are FOLDED rather than listed or
// dropped — see `syncRunRows.ts` for why both alternatives are worse.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { Card, CardContent } from "@/components/ui/card";
import { DataTable, type FilterDef } from "@/components/DataTable";
import { translateApiError } from "@/lib/api/errors";
import type { SyncRound } from "@/lib/api/sync";
import { useSyncRuns } from "@/lib/hooks/useSync";
import { formatDateTime } from "@/lib/utils";
import { SyncRunDetail } from "./SyncRunDetail";
import { SyncStatusSection } from "./SyncStatusSection";
import { rowStatus, syncRunColumns } from "./syncRunColumns";
import { ROUND_STATUSES, statusLabel } from "./syncRoundStatus";
import { rowSearchHaystack } from "./syncRunSearch";
import { collapseRepeats, groupSpan, type SyncRunRow } from "./syncRunRows";

interface Props {
  /** False while another tab is in front: no request, no discarded response. */
  enabled: boolean;
}

/** A folded row opened up: the rounds it stands in for. A stretch of failures
 *  shares one message — that is what let them fold — so it is stated once. */
function GroupDetail({ runs }: { runs: SyncRound[] }) {
  const { t } = useTranslation();
  const span = groupSpan(runs);
  const shared = runs[0]?.detail ?? null;
  return (
    <div className="space-y-2 px-4 py-3">
      <p className="text-sm text-muted-foreground">
        {t("sync.runs.foldedDetail", {
          count: span.count,
          from: formatDateTime(span.from),
          to: formatDateTime(span.to),
        })}
      </p>
      {shared ? <p className="font-mono text-xs text-destructive">{shared}</p> : null}
      <ul className="space-y-0.5 font-mono text-xs text-muted-foreground">
        {runs.map((run) => (
          <li key={`${run.id}-${run.finished_at}`}>{formatDateTime(run.finished_at)}</li>
        ))}
      </ul>
    </div>
  );
}

function RunsTable({ enabled }: Props) {
  const { t } = useTranslation();
  // isLoading, not isPending: a disabled query stays "pending" forever.
  const { data, isLoading, error } = useSyncRuns(enabled);
  const rows = useMemo(() => collapseRepeats(data?.rounds ?? []), [data]);

  const filters: FilterDef<SyncRunRow>[] = [
    {
      key: "status",
      label: t("sync.runs.filter"),
      allLabel: t("resources.status.all"),
      accessor: rowStatus,
      options: ROUND_STATUSES.map((s) => ({ value: s, label: statusLabel(t, s) })),
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
  // Rendered inside this tab, so a failing history never blanks the others.
  if (error) {
    return (
      <Card className="paper-card border-destructive/40">
        <CardContent className="py-4 text-destructive">{translateApiError(t, error)}</CardContent>
      </Card>
    );
  }
  return (
    <DataTable
      rows={rows}
      columns={syncRunColumns(t)}
      rowKey={(row) => row.id}
      search={{
        accessor: (row) => rowSearchHaystack(t, row),
        placeholder: t("sync.runs.searchPlaceholder"),
      }}
      filters={filters}
      getRowDetail={(row) =>
        row.kind === "run" ? <SyncRunDetail run={row.run} /> : <GroupDetail runs={row.runs} />
      }
      emptyMessage={t("sync.runs.empty")}
    />
  );
}

export function SyncRunsTab({ enabled }: Props) {
  return (
    <div className="space-y-6">
      <SyncStatusSection />
      <RunsTable enabled={enabled} />
    </div>
  );
}
