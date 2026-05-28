import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useRetentionPolicies,
  useUpdateRetentionPolicy,
  usePruneNow,
} from "@/lib/hooks/useRetention";
import { useDaemonBackup } from "@/lib/hooks/useDaemon";
import { translateApiError } from "@/lib/api/errors";
import { RetentionPolicySection } from "./RetentionPolicySection";

/**
 * The Data settings tab. Two cards — "Data retention" (a row per log
 * table plus the manual prune) and "Data backup" — both following one
 * layout rhythm: an explanation on the left, the action on the right.
 */
export function DataSettings() {
  const { t } = useTranslation();
  const { data, isPending, error } = useRetentionPolicies();
  const update = useUpdateRetentionPolicy();
  const prune = usePruneNow();
  const backup = useDaemonBackup();
  const [pruneResult, setPruneResult] = useState<string | null>(null);
  const [backupPath, setBackupPath] = useState<string | null>(null);

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

  return (
    <div className="space-y-6">
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
                  update.mutate({
                    tableName: policy.table_name,
                    retentionDays,
                  })
                }
                updating={update.isPending}
              />
            </div>
          ))}
          <div className="flex flex-col gap-3 p-6 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">
              {t("settings.retention.pruneDescription")}
            </p>
            <div className="flex shrink-0 flex-col items-start gap-1.5 sm:items-end">
              <Button
                onClick={() =>
                  prune.mutate(undefined, {
                    onSuccess: (result) => {
                      const summary = result
                        ? Object.entries(result.tables ?? {})
                            .map(([k, v]) => `${k}: ${v}`)
                            .join("; ")
                        : "no result";
                      setPruneResult(t("settings.retention.pruneResult", { summary }));
                    },
                  })
                }
                disabled={prune.isPending}
              >
                {prune.isPending
                  ? t("settings.retention.pruning")
                  : t("settings.retention.pruneAll")}
              </Button>
              {pruneResult ? <p className="text-xs text-muted-foreground">{pruneResult}</p> : null}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("settings.backup.title")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">{t("settings.backup.description")}</p>
            <div className="flex shrink-0 flex-col items-start gap-1.5 sm:items-end">
              <Button
                onClick={() =>
                  backup.mutate(undefined, {
                    onSuccess: (result) => setBackupPath(result?.path ?? null),
                  })
                }
                disabled={backup.isPending}
              >
                {backup.isPending ? t("settings.backup.creating") : t("settings.backup.create")}
              </Button>
              {backupPath ? (
                <p className="text-xs text-muted-foreground">
                  {t("settings.backup.saved", { path: backupPath })}
                </p>
              ) : null}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
