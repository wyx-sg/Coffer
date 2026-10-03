// src/components/settings/storage/HistoryBlock.tsx — Settings › Data's History block (canvas 1.4.11, 1.4.12).
//
// Spec web-ui "Group the Data tab by what kind of data it is": the retention
// of each record kind — changes, MCP calls and conversations — Keep forever or
// a number of days, cleaned up nightly, with Clear expired now. Every row
// auto-saves; a shortening asks first (RetentionPolicySection); a failed save
// says so above the blocks with Try again, and the row reads "Not saved".
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen } from "lucide-react";

import { LoadError } from "@/components/LoadError";
import { SettingRow } from "@/components/settings/SettingsLayout";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import {
  usePruneNow,
  useRetentionPolicies,
  useUpdateRetentionPolicy,
} from "@/lib/hooks/useRetention";
import { formatDateTime } from "@/lib/utils";
import { RetentionPolicySection } from "./RetentionPolicySection";
import { DataBlock } from "./DataBlock";

/** The record kinds the block shows, in the design's order; the other pruned tables keep their defaults. */
const SHOWN = ["audit_log", "mcp_invocations", "conversations"] as const;

interface Props {
  size: string | null;
  onReveal?: () => void;
}

export function HistoryBlock({ size, onReveal }: Props) {
  const { t } = useTranslation();
  const policies = useRetentionPolicies();
  const update = useUpdateRetentionPolicy();
  const prune = usePruneNow();
  const [confirmPrune, setConfirmPrune] = useState(false);
  const [pruneResult, setPruneResult] = useState<string | null>(null);

  const rows = SHOWN.map((name) =>
    policies.data?.policies.find((p) => p.table_name === name),
  ).filter((p): p is NonNullable<typeof p> => p !== undefined);
  const failedTable = update.isError ? update.variables?.tableName : undefined;
  // "MCP calls are still kept for 30 days." — what the refused save left in place.
  const failedPolicy = rows.find((p) => p.table_name === failedTable);
  const stillKept = failedPolicy
    ? t("settings.data.stillKept", {
        name: t(`settings.retention.policy.${failedPolicy.table_name}.name`, {
          defaultValue: failedPolicy.display_name,
        }),
        window:
          failedPolicy.retention_days === null
            ? t("settings.retention.foreverLower")
            : t("settings.retention.forDays", { count: failedPolicy.retention_days }),
      })
    : null;

  const pruned = rows.filter((p) => p.last_pruned_at);
  const lastAt = pruned
    .map((p) => p.last_pruned_at as string)
    .sort()
    .at(-1);
  const lastRows = pruned
    .filter((p) => p.last_pruned_at === lastAt)
    .reduce((sum, p) => sum + (p.last_pruned_rows ?? 0), 0);

  const summarise = (tables: Record<string, number>) => {
    const lines = Object.entries(tables)
      .filter(([, n]) => n > 0)
      .map(([table, n]) =>
        t("settings.retention.pruneRow", {
          rows: n,
          name: t(`settings.retention.policy.${table}.name`, { defaultValue: table }),
        }),
      );
    return lines.length > 0 ? lines.join("; ") : t("settings.retention.pruneNothing");
  };

  return (
    <>
      {update.isError ? (
        <Alert variant="destructive" data-testid="settings-data-save-failed">
          <AlertTitle>{t("settings.data.saveFailedTitle")}</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center gap-3">
            <span>
              {translateApiError(t, update.error)}
              {stillKept ? ` ${stillKept}` : null}
            </span>
            <Button
              size="sm"
              variant="outline"
              onClick={() => update.variables && update.mutate(update.variables)}
            >
              {t("settings.data.tryAgain")}
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      <DataBlock
        title={t("settings.data.history.title")}
        size={size}
        description={t("settings.data.history.description")}
        testId="settings-data-history"
        action={
          onReveal ? (
            <Button size="sm" variant="outline" onClick={onReveal}>
              <FolderOpen aria-hidden /> {t("settings.data.showInFinder")}
            </Button>
          ) : null
        }
      >
        {policies.isPending ? (
          <div className="flex flex-col gap-2 py-2.5">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : policies.error ? (
          <LoadError
            className="py-2.5"
            error={policies.error}
            onRetry={() => void policies.refetch()}
          />
        ) : (
          rows.map((policy) => (
            <RetentionPolicySection
              key={policy.table_name}
              policy={policy}
              failed={failedTable === policy.table_name}
              updating={update.isPending}
              onUpdate={(retentionDays) =>
                update.mutate({ tableName: policy.table_name, retentionDays })
              }
            />
          ))
        )}
        <SettingRow
          label={
            lastAt
              ? t("settings.data.lastCleared", { when: formatDateTime(lastAt), rows: lastRows })
              : t("settings.retention.neverPruned")
          }
          description={t("settings.data.clearedOnSchedule")}
          status={
            prune.isError ? (
              <span className="text-xs text-danger" role="alert">
                {translateApiError(t, prune.error)}
              </span>
            ) : pruneResult ? (
              <span className="text-xs text-text-muted" role="status">
                {pruneResult}
              </span>
            ) : null
          }
        >
          <Button
            variant="outline"
            onClick={() => setConfirmPrune(true)}
            disabled={prune.isPending}
          >
            {prune.isPending ? t("settings.retention.pruning") : t("settings.retention.pruneAll")}
          </Button>
        </SettingRow>
        <p
          className="border-t border-border-subtle py-3 text-xs text-text-muted"
          data-testid="settings-data-other-retention"
        >
          {t("settings.data.otherRetention")} <code className="font-mono">coffer config</code>
        </p>
      </DataBlock>
      <ConfirmDialog
        open={confirmPrune}
        onOpenChange={setConfirmPrune}
        title={t("settings.retention.pruneConfirmTitle")}
        description={t("settings.retention.pruneConfirmBody")}
        confirmLabel={t("settings.retention.pruneAll")}
        pending={prune.isPending}
        onConfirm={() => {
          setConfirmPrune(false);
          prune.mutate(undefined, {
            onSuccess: (result) => setPruneResult(summarise(result?.tables ?? {})),
          });
        }}
      />
    </>
  );
}
