// frontend/src/pages/settings/UpdatesSection.tsx
//
// Settings › About › Updates (spec web-ui "Check for and install updates on
// Settings › About"; design canvas 6.2.13–6.2.15). The shell does the checking
// and installing; this renders its record — up to date, a newer version with
// Download and restart, or a failed check that keeps the last good time — and
// asks it to act. A busy control shows it and takes no second press. In a
// browser there is nothing to control: a page the daemon serves cannot replace
// the app, so the section says who installs updates and offers no button.
import { useTranslation } from "react-i18next";
import { Download, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { useShellUpdates } from "@/lib/hooks/useShellUpdates";
import type { UpdateStatus } from "@/lib/shellUpdates";
import { formatDateTime, formatLocalDateTime } from "@/lib/utils";

function percent(status: UpdateStatus): string {
  const { downloaded, total } = status;
  return downloaded != null && total ? `${Math.floor((downloaded * 100) / total)}%` : "";
}

export function UpdatesSection() {
  const { t } = useTranslation();
  const { inShell, status, actionError, check, install, setAutoCheck } = useShellUpdates();

  if (!inShell || (status && !status.configured)) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.about.updates.title")}</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {inShell ? t("settings.about.updates.unconfigured") : t("settings.about.updates.browser")}
        </CardContent>
      </Card>
    );
  }

  const phase = status?.phase ?? "idle";
  const checking = phase === "checking";
  const downloading = phase === "downloading" || phase === "installing";
  const offer = status?.available ?? null;
  const failed = phase === "failed";
  const lastChecked = status?.lastCheckedAt
    ? t("settings.about.updates.lastChecked", {
        time: formatLocalDateTime(new Date(status.lastCheckedAt)),
      })
    : t("settings.about.updates.neverChecked");

  let headline: string;
  if (failed) {
    headline = offer ? t("settings.about.updates.installFailed") : t("settings.about.updates.failed");
  } else if (offer) {
    headline = t("settings.about.updates.available", { version: offer.version });
  } else if (status?.lastCheckedAt) {
    headline = t("settings.about.updates.upToDate");
  } else {
    headline = t("settings.about.updates.notChecked");
  }

  const detail = [
    offer?.date ? t("settings.about.updates.released", { date: formatDateTime(offer.date) }) : null,
    lastChecked,
    offer && !failed ? t("settings.about.updates.availableHelp") : null,
  ]
    .filter(Boolean)
    .join(" ");
  const error = actionError ?? (failed ? status?.error : null);
  const notes = (offer?.notes ?? "")
    .split("\n")
    .map((line) => line.replace(/^\s*[-*·]\s*/, "").trim())
    .filter(Boolean);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.about.updates.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 space-y-1">
            <p className="font-medium">{headline}</p>
            <p className="text-muted-foreground">{detail}</p>
            {error ? (
              <p className="text-destructive" role="alert">
                {error}{" "}
                {status
                  ? t("settings.about.updates.youAreOn", { version: status.currentVersion })
                  : null}
              </p>
            ) : null}
          </div>
          {offer ? (
            <Button size="sm" disabled={downloading || checking} onClick={() => void install()}>
              <Download aria-hidden />
              {phase === "installing"
                ? t("settings.about.updates.installing")
                : downloading
                  ? t("settings.about.updates.downloading", { pct: percent(status!) }).trim()
                  : t("settings.about.updates.download")}
            </Button>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              disabled={checking || !status}
              onClick={() => void check()}
            >
              <RefreshCw aria-hidden className={checking ? "animate-spin" : undefined} />
              {checking
                ? t("settings.about.updates.checking")
                : failed
                  ? t("settings.about.updates.tryAgain")
                  : t("settings.about.updates.check")}
            </Button>
          )}
        </div>

        {notes.length > 0 ? (
          <div className="space-y-1 rounded-md bg-muted px-3 py-2 text-muted-foreground">
            <p className="text-xs font-semibold uppercase">
              {t("settings.about.updates.whatsNew")}
            </p>
            <ul className="list-disc space-y-0.5 pl-4">
              {notes.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="flex items-center justify-between gap-4 border-t pt-4">
          <div className="space-y-0.5">
            <p className="font-medium">{t("settings.about.updates.auto")}</p>
            <p className="text-muted-foreground">{t("settings.about.updates.autoHelp")}</p>
          </div>
          <Switch
            checked={status?.autoCheck ?? true}
            disabled={!status}
            onCheckedChange={(checked) => void setAutoCheck(checked)}
            aria-label={t("settings.about.updates.auto")}
          />
        </div>
      </CardContent>
    </Card>
  );
}
