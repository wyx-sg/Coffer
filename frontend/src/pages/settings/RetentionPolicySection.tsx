// frontend/src/pages/settings/RetentionPolicySection.tsx
//
// One retention-policy row inside the "Data retention" card: the table's
// name, description, and last-prune status on the left; the keep-forever
// toggle and retention-days field on the right. Edits auto-save — toggling
// keep-forever persists immediately; the days field persists on blur (or
// Enter) — so there is no Save button, matching every other settings surface.
//
// Shortening the window is the one edit that costs data: the next prune
// deletes rows the old window kept. So a lower value (or turning keep-forever
// off) asks first, and cancelling puts the row back where it was. The display
// name and description are translated by `table_name`, falling back to the
// API-supplied text.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
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

const MIN_DAYS = 1;
const MAX_DAYS = 3650;

export function RetentionPolicySection({ policy, onUpdate, updating }: Props) {
  const { t } = useTranslation();
  const [keepForever, setKeepForever] = useState(policy.retention_days === null);
  const [days, setDays] = useState<number>(
    policy.retention_days ?? policy.default_retention_days ?? 30,
  );
  // A shorter window waiting for the user's confirmation, or null.
  const [proposed, setProposed] = useState<number | null>(null);
  // True after a typed value had to be raised to the minimum.
  const [clamped, setClamped] = useState(false);
  // Re-sync local form state when the upstream policy changes (e.g. after
  // an auto-save round-trip or a refetch landing a different value); without
  // this the row "remembers" the value from the first render forever.
  useEffect(() => {
    setKeepForever(policy.retention_days === null);
    setDays(policy.retention_days ?? policy.default_retention_days ?? 30);
  }, [policy.retention_days, policy.default_retention_days]);
  const foreverId = `forever-${policy.table_name}`;
  const daysId = `days-${policy.table_name}`;

  /** Shorter than what is stored — including "forever" becoming a number. */
  const shortens = (next: number) => policy.retention_days === null || next < policy.retention_days;

  const request = (next: number) => {
    if (shortens(next)) setProposed(next);
    else onUpdate(next);
  };

  // Toggling keep-forever ON clears the window (null) right away; OFF is a
  // shortening, so it goes through the confirmation like any other.
  const toggleForever = (next: boolean) => {
    setKeepForever(next);
    if (next) onUpdate(null);
    else request(days);
  };

  // Persist the days field only once the user finishes editing it (blur/Enter),
  // and only when it actually differs from what's stored — avoids a write per
  // keystroke and a redundant round-trip on a no-op blur.
  const commitDays = () => {
    if (!keepForever && days !== policy.retention_days) request(days);
  };

  const cancel = () => {
    setProposed(null);
    setKeepForever(policy.retention_days === null);
    setDays(policy.retention_days ?? policy.default_retention_days ?? 30);
  };

  const confirm = () => {
    if (proposed !== null) onUpdate(proposed);
    setProposed(null);
  };

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
          {policy.last_pruned_at
            ? t("settings.retention.lastPruned", {
                when: formatDateTime(policy.last_pruned_at),
                rows: policy.last_pruned_rows,
              })
            : t("settings.retention.neverPruned")}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="flex items-center gap-2">
            <Switch
              id={foreverId}
              checked={keepForever}
              disabled={updating}
              onCheckedChange={toggleForever}
            />
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
                min={MIN_DAYS}
                max={MAX_DAYS}
                value={days}
                disabled={updating}
                onChange={(e) => {
                  const raw = parseInt(e.target.value || "0", 10) || 0;
                  setClamped(raw < MIN_DAYS);
                  setDays(Math.min(MAX_DAYS, Math.max(MIN_DAYS, raw)));
                }}
                onBlur={commitDays}
                onKeyDown={(e) => {
                  if (e.key === "Enter") e.currentTarget.blur();
                }}
                className="w-20"
              />
            </div>
          ) : null}
        </div>
        {clamped && !keepForever ? (
          <p className="text-xs text-status-warn" role="status">
            {t("settings.retention.minDays")}
          </p>
        ) : null}
      </div>

      <ConfirmDialog
        open={proposed !== null}
        onOpenChange={(open) => {
          if (!open) cancel();
        }}
        title={t("settings.retention.shortenTitle", { days: proposed ?? days })}
        description={t("settings.retention.shortenBody")}
        confirmLabel={t("settings.retention.shortenConfirm")}
        pending={updating}
        onConfirm={confirm}
      />
    </div>
  );
}
