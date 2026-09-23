// frontend/src/pages/sync/SyncJoinReport.tsx
//
// The join, stated (spec vault-sync "Report a join before applying it"): when
// this machine last converged, how many documents the remote changed since,
// how many this vault holds. One rendering for the three places it appears —
// the join dialog, the Setup card on a machine that has not joined, and an
// `awaiting_join` round in the history — so they cannot say it differently.
import { useTranslation } from "react-i18next";

import type { JoinPreview } from "@/lib/api/sync";

export function SyncJoinReport({ report }: { report: JoinPreview }) {
  const { t } = useTranslation();
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm" data-testid="sync-join">
      <dt className="text-muted-foreground">{t("sync.join.lastConverged")}</dt>
      <dd>{report.last_converged_on ?? t("sync.join.never")}</dd>
      {report.remote_changed != null ? (
        <>
          <dt className="text-muted-foreground">{t("sync.join.remoteChanged")}</dt>
          <dd>{report.remote_changed}</dd>
        </>
      ) : null}
      <dt className="text-muted-foreground">{t("sync.join.vaultDocuments")}</dt>
      <dd>{report.vault_documents ?? 0}</dd>
    </dl>
  );
}
