// frontend/src/pages/sync/SyncStatusCard.tsx
//
// Whether sync is working, in one card: when the last round ran and what it
// moved, when the next one runs, how many machines share the remote, what the
// vault holds that syncs — and "Sync now". A problem, when there is one, sits
// on top of it, because it is the first thing the numbers below depend on.
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SyncStatus } from "@/lib/api/sync";
import { useRunSync } from "@/lib/hooks/useSync";
import { formatDateTime } from "@/lib/utils";
import { SyncProblemBanner } from "./SyncProblemBanner";

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

export function SyncStatusCard({ status }: { status: SyncStatus }) {
  const { t } = useTranslation();
  const run = useRunSync();
  const last = status.last_round;
  const running = run.isPending || status.running_since !== null;
  const { areas } = status;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
        <CardTitle>{t("sync.status.title")}</CardTitle>
        <Button
          type="button"
          variant="secondary"
          disabled={!status.configured || !status.joined || running}
          onClick={() => run.mutate()}
        >
          <RefreshCw className="size-4" aria-hidden />
          {running ? t("sync.status.syncing") : t("sync.status.syncNow")}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {status.problem ? (
          <SyncProblemBanner
            problem={status.problem}
            vaultPath={status.vault_path}
            synchroniser={status.synchroniser}
          />
        ) : null}
        {!status.configured ? (
          <p className="text-sm text-muted-foreground">{t("sync.status.notConfigured")}</p>
        ) : null}
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4" data-testid="sync-status-facts">
          <Fact label={t("sync.status.lastRound")}>
            {last ? formatDateTime(last.finished_at) : t("sync.status.never")}
          </Fact>
          <Fact label={t("sync.status.moved")}>
            {last
              ? t("sync.status.movedValue", {
                  pulled: last.pulled_files,
                  pushed: last.pushed_files,
                })
              : "—"}
          </Fact>
          <Fact label={t("sync.status.nextRound")}>
            {status.next_round_at ? formatDateTime(status.next_round_at) : "—"}
          </Fact>
          <Fact label={t("sync.status.machines")}>{status.machines}</Fact>
          <Fact label={t("sync.status.knowledge")}>{areas.knowledge_documents}</Fact>
          <Fact label={t("sync.status.skills")}>{areas.skills}</Fact>
          <Fact label={t("sync.status.resources")}>{areas.resources}</Fact>
          <Fact label={t("sync.status.secrets")}>
            {t(areas.secrets_synced ? "sync.status.secretsSynced" : "sync.status.secretsLocal", {
              count: areas.secrets,
            })}
          </Fact>
        </dl>
      </CardContent>
    </Card>
  );
}
