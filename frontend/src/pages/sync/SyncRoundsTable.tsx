// frontend/src/pages/sync/SyncRoundsTable.tsx
//
// "Rounds" on the Status tab (6.5.01): every round this Mac has run, newest
// first, in the shared DataTable — without a search box or a status filter,
// because the boards draw none: rounds that repeated one outcome are FOLDED
// instead (see `syncRunRows.ts` for why listing or dropping them is worse),
// which is what keeps the history short enough to read.
//
// A row opens the round's drawer (6.5.04); Roll back, on the row or in the
// drawer, asks first with the plan the daemon states (6.5.10).
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { DataTable } from "@/components/DataTable";
import { translateApiError } from "@/lib/api/errors";
import type { SyncRound } from "@/lib/api/sync";
import { SyncRollbackDialog } from "./SyncRollbackAction";
import { SyncRunDetail } from "./SyncRunDetail";
import { syncRunColumns } from "./syncRunColumns";
import { collapseRepeats, type SyncRunRow } from "./syncRunRows";

interface Props {
  runs: SyncRound[];
  isLoading: boolean;
  error: unknown;
  nextRoundAt: string | null;
}

export function SyncRoundsTable({ runs, isLoading, error, nextRoundAt }: Props) {
  const { t } = useTranslation();
  const rows = useMemo(() => collapseRepeats(runs), [runs]);
  const [open, setOpen] = useState<SyncRunRow | null>(null);
  const [rollingBack, setRollingBack] = useState<(SyncRound & { id: number }) | null>(null);

  const columns = syncRunColumns(t, { runs, nextRoundAt, onRollback: setRollingBack });

  return (
    <section className="space-y-2.5" aria-labelledby="sync-rounds-title">
      <div className="flex min-h-[26px] flex-wrap items-center gap-x-2">
        <h2 id="sync-rounds-title" className="text-sm font-semibold text-text">
          {t("sync.rounds.title")}
        </h2>
        <span className="text-xs text-text-subtle">{t("sync.rounds.hint")}</span>
      </div>
      {/* Rendered inside the tab, so a failing history never blanks the page. */}
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {translateApiError(t, error)}
        </p>
      ) : (
        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(row) => row.id}
          onRowClick={setOpen}
          isLoading={isLoading}
          emptyMessage={t("sync.rounds.empty")}
        />
      )}
      <SyncRunDetail
        row={open}
        onClose={() => setOpen(null)}
        onOpen={setOpen}
        onRollback={(run) => {
          setOpen(null);
          setRollingBack(run);
        }}
      />
      <SyncRollbackDialog run={rollingBack} onClose={() => setRollingBack(null)} />
    </section>
  );
}
