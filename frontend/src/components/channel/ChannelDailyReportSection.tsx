// frontend/src/components/channel/ChannelDailyReportSection.tsx — the daily report on a channel's Overview: off, or every day at a time, sent to the owner's direct chat.
//
// Spec channels "Write the daily report from the day's channel conversations".
// The report is a scheduled task made from a template; this card sets it up,
// moves its time, and switches it off (pause) or on again. Its prompt and the
// rest are edited on the Scheduled tasks page, which Open task leads to. Set
// up needs the channel paired with its owner: the report goes to their direct
// chat.
import { CircleAlert } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { SettingsSection } from "@/components/settings/SettingsLayout";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { useDisableResource, useEnableResource } from "@/lib/hooks/useResourceMutations";
import {
  SCHEDULED_TASK_KIND,
  useScheduledTasks,
  useSetDailyReport,
} from "@/lib/hooks/useScheduledTasks";

const DEFAULT_TIME = "18:00";

export function ChannelDailyReportSection({ channelUid }: { channelUid: string }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { data } = useScheduledTasks();
  const report = data?.find(
    (x) => x.config.template === "daily_report" && x.config.chat.channel === channelUid,
  );
  const current = report?.config.schedule.kind === "daily" ? report.config.schedule.time : null;
  const [time, setTime] = useState<string | null>(null);
  const shown = time ?? current ?? DEFAULT_TIME;
  const save = useSetDailyReport();
  const enable = useEnableResource();
  const disable = useDisableResource();
  const on = !!report?.enabled;

  const submit = () =>
    save.mutate(
      { channel: channelUid, time: shown },
      {
        onSuccess: () => {
          setTime(null);
          toast.success(t("scheduledTasks.dailyReport.saved", { time: shown }));
        },
      },
    );

  return (
    <SettingsSection
      title={t("scheduledTasks.dailyReport.title")}
      description={t("scheduledTasks.dailyReport.help")}
      headingLevel={3}
      testId="channel-daily-report"
      action={
        report ? (
          <Switch
            aria-label={t("scheduledTasks.dailyReport.title")}
            checked={on}
            disabled={enable.isPending || disable.isPending}
            onCheckedChange={(v) =>
              (v ? enable : disable).mutate({ kind: SCHEDULED_TASK_KIND, uid: report.uid })
            }
          />
        ) : null
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-text">
          {on && current
            ? t("scheduledTasks.dailyReport.on", { time: current })
            : t("scheduledTasks.dailyReport.off")}
        </span>
        <Input
          type="time"
          aria-label={t("scheduledTasks.dailyReport.time")}
          className="ml-auto w-28"
          value={shown}
          onChange={(e) => setTime(e.target.value)}
        />
        <Button
          size="sm"
          variant="outline"
          disabled={save.isPending || (on && shown === current)}
          onClick={submit}
        >
          {report && on
            ? t("scheduledTasks.dailyReport.save")
            : t("scheduledTasks.dailyReport.set")}
        </Button>
        {report ? (
          <Link
            to={`/scheduled-tasks/${encodeURIComponent(report.uid)}`}
            className="text-sm font-label text-accent-text hover:underline"
          >
            {t("scheduledTasks.dailyReport.open")}
          </Link>
        ) : null}
      </div>
      {save.error ? (
        <Alert variant="error" className="mt-2">
          <CircleAlert aria-hidden />
          <AlertTitle>{t("scheduledTasks.dailyReport.failed")}</AlertTitle>
          <AlertDescription>{translateApiError(t, save.error)}</AlertDescription>
        </Alert>
      ) : null}
    </SettingsSection>
  );
}
