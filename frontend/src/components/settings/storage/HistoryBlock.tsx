// src/components/settings/storage/HistoryBlock.tsx — Settings › Data's History block (canvas 1.4.11, 1.4.12).
//
// Spec web-ui "Group the Data tab by what kind of data it is": the retention
// of each record kind — changes, MCP calls and conversations — Keep forever or
// a number of days, cleaned up nightly, with Clear expired now (which also
// clears expired attachments, a row of Local content). Every row auto-saves; a
// shortening asks first (RetentionPolicySection); a failed save is announced
// by RetentionSaveFailed above the blocks, and the row reads "Not saved".
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen } from "lucide-react";

import { LoadError } from "@/components/LoadError";
import { SettingRow } from "@/components/settings/SettingsLayout";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { abbreviateHomePath } from "@/lib/agents/display";
import { translateApiError } from "@/lib/api/errors";
import {
  usePruneNow,
  useRetentionPolicies,
  type useUpdateRetentionPolicy,
} from "@/lib/hooks/useRetention";
import { formatMoment } from "@/lib/time";
import { RetentionPolicySection } from "./RetentionPolicySection";
import { DataBlock } from "./DataBlock";

/** The record kinds the block shows, in the design's order; the other pruned tables keep their defaults. */
const SHOWN = ["audit_log", "mcp_invocations", "conversations"] as const;

interface Props {
  size: string | null;
  /** The records' folder, named in the reveal button's tooltip. */
  path?: string;
  onReveal?: () => void;
  /** The save mutation, shared with the attachments row so one notice covers both. */
  update: ReturnType<typeof useUpdateRetentionPolicy>;
}

export function HistoryBlock({ size, path, onReveal, update }: Props) {
  const { t, i18n } = useTranslation();
  const policies = useRetentionPolicies();
  const prune = usePruneNow();
  const [confirmPrune, setConfirmPrune] = useState(false);
  const [pruneResult, setPruneResult] = useState<string | null>(null);

  const rows = SHOWN.map((name) =>
    policies.data?.policies.find((p) => p.table_name === name),
  ).filter((p): p is NonNullable<typeof p> => p !== undefined);
  const failedTable = update.isError ? update.variables?.tableName : undefined;

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
        t(`settings.retention.policy.${table}.pruneRow`, {
          rows: n,
          name: t(`settings.retention.policy.${table}.name`, { defaultValue: table }),
          defaultValue: t("settings.retention.pruneRow", {
            rows: n,
            name: t(`settings.retention.policy.${table}.name`, { defaultValue: table }),
          }),
        }),
      );
    return lines.length > 0 ? lines.join("; ") : t("settings.retention.pruneNothing");
  };

  return (
    <>
      <DataBlock
        title={t("settings.data.history.title")}
        size={size}
        description={t("settings.data.history.description")}
        testId="settings-data-history"
        action={
          onReveal ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button size="sm" variant="outline" onClick={onReveal}>
                  <FolderOpen aria-hidden /> {t("settings.data.showInFinder")}
                </Button>
              </TooltipTrigger>
              {path ? (
                <TooltipContent className="font-mono">{abbreviateHomePath(path)}</TooltipContent>
              ) : null}
            </Tooltip>
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
              ? t("settings.data.lastCleared", {
                  when: formatMoment(lastAt, i18n.language, t),
                  rows: lastRows,
                })
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
