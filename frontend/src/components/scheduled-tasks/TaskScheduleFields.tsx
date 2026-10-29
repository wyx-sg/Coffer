// src/components/scheduled-tasks/TaskScheduleFields.tsx — the When block of the task dialog: how often, and the time, minute, weekday, moment or cron line it needs.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ScheduleKind } from "@/lib/api/scheduledTasks";
import { SCHEDULE_KINDS, weekdayName, type TaskForm } from "@/lib/scheduledTasks/format";

interface Props {
  form: TaskForm;
  set: (patch: Partial<TaskForm>) => void;
}

export function TaskScheduleFields({ form, set }: Props) {
  const { t, i18n } = useTranslation();
  const needsTime = form.kind === "daily" || form.kind === "weekdays" || form.kind === "weekly";
  return (
    <div className="space-y-1.5">
      <Label htmlFor="task-kind">{t("scheduledTasks.dialog.when")}</Label>
      <div className="flex flex-wrap gap-2">
        <Select value={form.kind} onValueChange={(v) => set({ kind: v as ScheduleKind })}>
          <SelectTrigger id="task-kind" className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SCHEDULE_KINDS.map((k) => (
              <SelectItem key={k} value={k}>
                {t(`scheduledTasks.dialog.kind.${k}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {form.kind === "weekly" ? (
          <Select value={String(form.weekday)} onValueChange={(v) => set({ weekday: Number(v) })}>
            <SelectTrigger aria-label={t("scheduledTasks.dialog.weekday")} className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[0, 1, 2, 3, 4, 5, 6].map((d) => (
                <SelectItem key={d} value={String(d)}>
                  {weekdayName(d, i18n.language)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}
        {needsTime ? (
          <Input
            type="time"
            aria-label={t("scheduledTasks.dialog.time")}
            className="w-28"
            value={form.time}
            onChange={(e) => set({ time: e.target.value })}
          />
        ) : null}
        {form.kind === "hourly" ? (
          <Input
            type="number"
            min={0}
            max={59}
            aria-label={t("scheduledTasks.dialog.minute")}
            className="w-24"
            value={form.minute}
            onChange={(e) => set({ minute: e.target.value })}
          />
        ) : null}
        {form.kind === "once" ? (
          <Input
            type="datetime-local"
            aria-label={t("scheduledTasks.dialog.at")}
            className="w-56"
            value={form.at}
            onChange={(e) => set({ at: e.target.value })}
          />
        ) : null}
        {form.kind === "cron" ? (
          <Input
            aria-label={t("scheduledTasks.dialog.cron")}
            className="w-44 font-mono"
            value={form.expr}
            onChange={(e) => set({ expr: e.target.value })}
          />
        ) : null}
      </div>
      <p className="text-xs text-text-muted">
        {form.kind === "cron"
          ? t("scheduledTasks.dialog.cronHint")
          : form.kind === "manual"
            ? t("scheduledTasks.dialog.manualHint")
            : t("scheduledTasks.dialog.localTime")}
      </p>
    </div>
  );
}
