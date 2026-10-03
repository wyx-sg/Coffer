// src/components/settings/storage/RetentionShortenDialog.tsx — the confirmation a shorter retention window asks for (canvas 1.4.12).
//
// It counts, through the daemon's preview read, how many records the next
// cleanup would delete and how many the table holds now and after, before the
// new window is saved (spec resource-framework "Prune each registered log
// table on its own retention period").
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { components } from "@/lib/api/types";
import { useRetentionPreview } from "@/lib/hooks/useRetention";

type RetentionPolicyOut = components["schemas"]["RetentionPolicyOut"];

/** "Keep MCP calls for 7 days?" — what the shorter window deletes, counted before it is saved. */
export function RetentionShortenDialog({
  policy,
  proposed,
  updating,
  onCancel,
  onConfirm,
}: {
  policy: RetentionPolicyOut;
  proposed: number | null;
  updating: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { t } = useTranslation();
  const preview = useRetentionPreview(policy.table_name, proposed);
  const days = proposed ?? 0;
  const key = `settings.retention.policy.${policy.table_name}`;
  const unit = (count: number) =>
    t(`${key}.unit`, { count, defaultValue: t("settings.retention.rows", { count }) });
  const counts = preview.data;
  const kept = counts ? counts.total_rows - counts.rows_to_delete : 0;
  const fmt = (n: number) => n.toLocaleString();

  return (
    <ConfirmDialog
      open={proposed !== null}
      onOpenChange={(open) => {
        if (!open) onCancel();
      }}
      title={t(`${key}.shortenTitle`, {
        days,
        defaultValue: t("settings.retention.shortenTitle", { days }),
      })}
      description={
        counts
          ? t("settings.retention.shortenCounted", {
              count: counts.rows_to_delete,
              rows: `${fmt(counts.rows_to_delete)} ${unit(counts.rows_to_delete)}`,
              days,
            })
          : t("settings.retention.shortenBody")
      }
      confirmLabel={t("settings.retention.shortenConfirmDays", { count: days })}
      pending={updating}
      onConfirm={onConfirm}
    >
      {counts ? (
        <dl className="flex flex-col gap-1 rounded-md bg-surface-sunken px-3 py-2 text-xs">
          <div className="flex gap-3">
            <dt className="w-14 text-text-muted">{t("settings.retention.now")}</dt>
            <dd className="text-text" data-testid="retention-shorten-now">
              {policy.retention_days === null
                ? t("settings.retention.forever")
                : t("settings.retention.daysCount", { count: policy.retention_days })}
              {" · "}
              {fmt(counts.total_rows)} {unit(counts.total_rows)}
            </dd>
          </div>
          <div className="flex gap-3">
            <dt className="w-14 text-text-muted">{t("settings.retention.after")}</dt>
            <dd className="text-text" data-testid="retention-shorten-after">
              {t("settings.retention.daysCount", { count: days })}
              {" · "}
              {t("settings.retention.about", { rows: `${fmt(kept)} ${unit(kept)}` })}
            </dd>
          </div>
        </dl>
      ) : null}
    </ConfirmDialog>
  );
}
