import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { formatDateTime } from "@/lib/utils";
import type { components } from "@/lib/api/types";

type RetentionPolicyOut = components["schemas"]["RetentionPolicyOut"];

interface Props {
  policy: RetentionPolicyOut;
  onUpdate: (retentionDays: number | null) => void;
  updating: boolean;
}

/**
 * One retention-policy row inside the "Data retention" card: the table's
 * name, description, and last-prune status on the left; the keep-forever
 * toggle, retention-days field, and Save button on the right. The display
 * name and description are translated by `table_name`, falling back to
 * the API-supplied text.
 */
export function RetentionPolicySection({ policy, onUpdate, updating }: Props) {
  const { t } = useTranslation();
  const [keepForever, setKeepForever] = useState(policy.retention_days === null);
  const [days, setDays] = useState<number>(
    policy.retention_days ?? policy.default_retention_days ?? 30,
  );
  // Re-sync local form state when the upstream policy changes (e.g. after
  // a Save round-trip or a refetch landing a different value); without
  // this the row "remembers" the value from the first render forever.
  useEffect(() => {
    setKeepForever(policy.retention_days === null);
    setDays(policy.retention_days ?? policy.default_retention_days ?? 30);
  }, [policy.retention_days, policy.default_retention_days]);
  const dirty =
    keepForever !== (policy.retention_days === null) ||
    (!keepForever && days !== policy.retention_days);
  const foreverId = `forever-${policy.table_name}`;
  const daysId = `days-${policy.table_name}`;

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 space-y-1">
        <div className="font-medium">
          {t(`settings.retention.policy.${policy.table_name}.name`, {
            defaultValue: policy.display_name,
          })}
        </div>
        <p className="text-sm text-muted-foreground">
          {t(`settings.retention.policy.${policy.table_name}.description`, {
            defaultValue: policy.description,
          })}
        </p>
        <p className="text-xs text-muted-foreground">
          {t("settings.retention.lastPruned", {
            when: policy.last_pruned_at
              ? formatDateTime(policy.last_pruned_at)
              : t("settings.retention.never"),
            rows: policy.last_pruned_rows,
          })}
        </p>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex items-center gap-2">
          <Switch id={foreverId} checked={keepForever} onCheckedChange={setKeepForever} />
          <Label htmlFor={foreverId}>{t("settings.retention.keepForever")}</Label>
        </div>
        {!keepForever ? (
          <div className="flex items-center gap-2">
            <Label htmlFor={daysId} className="whitespace-nowrap">
              {t("settings.retention.days")}
            </Label>
            <Input
              id={daysId}
              type="number"
              min={1}
              max={3650}
              value={days}
              onChange={(e) => setDays(Math.max(1, parseInt(e.target.value || "0", 10) || 1))}
              className="w-20"
            />
          </div>
        ) : null}
        <Button
          size="sm"
          disabled={!dirty || updating}
          onClick={() => onUpdate(keepForever ? null : days)}
        >
          {updating ? t("common.saving") : t("common.save")}
        </Button>
      </div>
    </div>
  );
}
