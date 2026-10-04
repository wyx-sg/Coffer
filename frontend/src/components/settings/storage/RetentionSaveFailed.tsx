// src/components/settings/storage/RetentionSaveFailed.tsx — the notice above Settings › Data's blocks when a retention save failed.
//
// Spec web-ui "Group the Data tab by what kind of data it is": a failed save
// says so above the blocks with Try again, and the row reads "Not saved".
import { useTranslation } from "react-i18next";
import { TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import { useRetentionPolicies, type useUpdateRetentionPolicy } from "@/lib/hooks/useRetention";

export function RetentionSaveFailed({
  update,
}: {
  update: ReturnType<typeof useUpdateRetentionPolicy>;
}) {
  const { t } = useTranslation();
  const policies = useRetentionPolicies();
  if (!update.isError) return null;
  // "MCP calls are still kept for 30 days." — what the refused save left in place.
  const failedPolicy = policies.data?.policies.find(
    (p) => p.table_name === update.variables?.tableName,
  );
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
  return (
    <div
      role="alert"
      className="flex items-start gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5"
      data-testid="settings-data-save-failed"
    >
      <TriangleAlert aria-hidden className="mt-px size-[15px] shrink-0 text-danger" />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-sm font-label text-text">{t("settings.data.saveFailedTitle")}</span>
        <span className="text-xs text-text-muted">
          {translateApiError(t, update.error)}
          {stillKept ? ` ${stillKept}` : null}
        </span>
      </div>
      <Button
        size="sm"
        variant="outline"
        onClick={() => update.variables && update.mutate(update.variables)}
      >
        {t("settings.data.tryAgain")}
      </Button>
    </div>
  );
}
