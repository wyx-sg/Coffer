// frontend/src/pages/sync/SyncRoundsTable.tsx
//
// "Rounds" on the Status tab (6.4.01): every round this Mac has run, newest
// first, in the shared DataTable — without a search box or a status filter,
// because the boards draw none: rounds that repeated one outcome are FOLDED
// instead (see `syncRunRows.ts` for why listing or dropping them is worse),
// which is what keeps the history short enough to read.
//
// A row opens the round's drawer (6.4.04); Roll back lives only there, and
// asks first with the plan the daemon states (6.4.12).
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { RotateCcw } from "lucide-react";

import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { Section } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import type { SyncRound } from "@/lib/api/sync";
import { SyncRollbackDialog } from "./SyncRollbackAction";
import { SyncRunDetail } from "./SyncRunDetail";
import { syncRunColumns } from "./syncRunColumns";
import { collapseRepeats, type SyncRunRow } from "./syncRunRows";

interface Props {
  runs: SyncRound[];
  /** The count of every round, and the cursor paging over them. */
  total?: number;
  hasMore: boolean;
  isLoadingMore: boolean;
  onLoadMore: () => void;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
  nextRoundAt: string | null;
}

export function SyncRoundsTable({
  runs,
  total,
  hasMore,
  isLoadingMore,
  onLoadMore,
  isLoading,
  error,
  onRetry,
  nextRoundAt,
}: Props) {
  const { t } = useTranslation();
  const rows = useMemo(() => collapseRepeats(runs), [runs]);
  const [open, setOpen] = useState<SyncRunRow | null>(null);
  const [rollingBack, setRollingBack] = useState<(SyncRound & { id: number }) | null>(null);

  const columns = syncRunColumns(t, { runs, nextRoundAt });

  return (
    <Section title={t("sync.rounds.title")} as="h2" labelled testId="sync-rounds">
      {/* Rendered inside the tab, so a failing history never blanks the page. */}
      {error ? (
        <EmptyState
          tone="error"
          size="compact"
          title={t("sync.rounds.loadFailed")}
          description={translateApiError(t, error)}
          action={
            <Button variant="outline" size="sm" onClick={onRetry}>
              <RotateCcw aria-hidden /> {t("common.retry")}
            </Button>
          }
        />
      ) : (
        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(row) => row.id}
          onRowClick={setOpen}
          isLoading={isLoading}
          infinite={{
            loaded: runs.length,
            total,
            hasMore,
            loading: isLoadingMore,
            onMore: onLoadMore,
            countLabel: (loaded, count) =>
              count === undefined
                ? t("sync.rounds.loadedCount", { loaded })
                : t("sync.rounds.loadedOfTotal", { loaded, total: count }),
          }}
          emptyMessage={t("sync.rounds.empty")}
        />
      )}
      <SyncRunDetail
        row={open}
        rows={rows}
        onClose={() => setOpen(null)}
        onOpen={setOpen}
        onRollback={(run) => {
          setOpen(null);
          setRollingBack(run);
        }}
      />
      <SyncRollbackDialog run={rollingBack} onClose={() => setRollingBack(null)} />
    </Section>
  );
}
