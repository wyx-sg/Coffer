// frontend/src/pages/settings/DataSettings.tsx
//
// The Data settings tab: the "Data retention" card — a row per log table
// plus the manual prune — following one layout rhythm: an explanation on
// the left, the action on the right. Every row auto-saves and says so with a
// toast; the manual prune confirms first, because it deletes rows right now.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import {
  useRetentionPolicies,
  useUpdateRetentionPolicy,
  usePruneNow,
} from "@/lib/hooks/useRetention";
import { RetentionPolicySection } from "./RetentionPolicySection";

export function DataSettings() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { data, isPending, error } = useRetentionPolicies();
  const update = useUpdateRetentionPolicy();
  const prune = usePruneNow();
  const [pruneResult, setPruneResult] = useState<string | null>(null);
  const [confirmPrune, setConfirmPrune] = useState(false);

  if (isPending)
    return (
      <Card>
        <CardContent className="py-6">{t("common.loading")}</CardContent>
      </Card>
    );
  if (error)
    return (
      <Card>
        <CardContent className="py-6 text-destructive">{translateApiError(t, error)}</CardContent>
      </Card>
    );

  // One line per table that lost rows, named the way the rows above name it —
  // never the raw table name. Nothing removed anywhere is its own message.
  const summarise = (tables: Record<string, number>) => {
    const lines = Object.entries(tables)
      .filter(([, rows]) => rows > 0)
      .map(([table, rows]) =>
        t("settings.retention.pruneRow", {
          rows,
          name: t(`settings.retention.policy.${table}.name`, { defaultValue: table }),
        }),
      );
    return lines.length > 0 ? lines.join("; ") : t("settings.retention.pruneNothing");
  };

  const runPrune = () => {
    setConfirmPrune(false);
    prune.mutate(undefined, {
      onSuccess: (result) => setPruneResult(summarise(result?.tables ?? {})),
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.retention.title")}</CardTitle>
      </CardHeader>
      <CardContent className="divide-y divide-border p-0">
        {data!.policies.map((policy) => (
          <div key={policy.table_name} className="p-6">
            <RetentionPolicySection
              policy={policy}
              onUpdate={(retentionDays) =>
                update.mutate(
                  { tableName: policy.table_name, retentionDays },
                  { onSuccess: () => toast.success(t("common.saved")) },
                )
              }
              updating={update.isPending}
            />
          </div>
        ))}
        {update.isError ? (
          <p className="px-6 py-3 text-xs text-destructive" role="alert">
            {translateApiError(t, update.error)}
          </p>
        ) : null}
        <div className="flex flex-col gap-3 p-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">
            {t("settings.retention.pruneDescription")}
          </p>
          <div className="flex shrink-0 flex-col items-start gap-1.5 sm:items-end">
            <Button onClick={() => setConfirmPrune(true)} disabled={prune.isPending}>
              {prune.isPending ? t("settings.retention.pruning") : t("settings.retention.pruneAll")}
            </Button>
            {prune.isError ? (
              <p className="text-xs text-destructive" role="alert">
                {translateApiError(t, prune.error)}
              </p>
            ) : pruneResult ? (
              <p className="text-xs text-muted-foreground" role="status">
                {pruneResult}
              </p>
            ) : null}
          </div>
        </div>
      </CardContent>

      <ConfirmDialog
        open={confirmPrune}
        onOpenChange={setConfirmPrune}
        title={t("settings.retention.pruneConfirmTitle")}
        description={t("settings.retention.pruneConfirmBody")}
        confirmLabel={t("settings.retention.pruneAll")}
        pending={prune.isPending}
        onConfirm={runPrune}
      />
    </Card>
  );
}
