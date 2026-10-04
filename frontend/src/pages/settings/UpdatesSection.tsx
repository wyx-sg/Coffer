// frontend/src/pages/settings/UpdatesSection.tsx
//
// Settings › About › Updates (spec web-ui "Check for and install updates on
// Settings › About"; canvas 1.4.23–1.4.26), an ordinary section: its title, then
// a hairline-topped status row and the automatic-check row. The shell does the checking
// and installing; this renders its record — up to date, a newer version with
// Download and restart, or a failed check that keeps the last good time — and
// asks it to act. A busy control shows it and takes no second press. In a
// browser there is nothing to control: a page the daemon serves cannot replace
// the app, so the section says who installs updates and offers no update
// button — only the daemon's hand-off that has an agent upgrade this copy the
// way it was installed (`GET /daemon/upgrade`).
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Download, RefreshCw } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useUpgradeHandoff } from "@/lib/hooks/useDaemon";
import { useShellUpdates } from "@/lib/hooks/useShellUpdates";
import type { UpdateStatus } from "@/lib/shellUpdates";
import { formatClockOrMoment, formatDay } from "@/lib/time";

function percent(status: UpdateStatus): string {
  const { downloaded, total } = status;
  return downloaded != null && total ? `${Math.floor((downloaded * 100) / total)}%` : "";
}

export function UpdatesSection() {
  const { t, i18n } = useTranslation();
  const { inShell, status, actionError, check, install, setAutoCheck } = useShellUpdates();
  const upgrade = useUpgradeHandoff(!inShell);

  if (!inShell || (status && !status.configured)) {
    return (
      <UpdatesBlock>
        <div className="space-y-3 text-sm text-text-muted">
          <p>
            {inShell
              ? t("settings.about.updates.unconfigured")
              : t("settings.about.updates.browser")}
          </p>
          {!inShell && upgrade.data ? <AgentHandoff prompt={upgrade.data} size="sm" /> : null}
        </div>
      </UpdatesBlock>
    );
  }

  const phase = status?.phase ?? "idle";
  const checking = phase === "checking";
  const downloading = phase === "downloading" || phase === "installing";
  const offer = status?.available ?? null;
  const failed = phase === "failed";
  const lastChecked = status?.lastCheckedAt
    ? t("settings.about.updates.lastChecked", {
        time: formatClockOrMoment(new Date(status.lastCheckedAt), i18n.language, t),
      })
    : t("settings.about.updates.neverChecked");

  let headline: string;
  if (failed) {
    headline = offer
      ? t("settings.about.updates.installFailed")
      : t("settings.about.updates.failed");
  } else if (offer) {
    headline = t("settings.about.updates.available", { version: offer.version });
  } else if (status?.lastCheckedAt) {
    headline = t("settings.about.updates.upToDate");
  } else {
    headline = t("settings.about.updates.notChecked");
  }

  const releaseDate = offer?.date ? new Date(offer.date) : null;
  const releasedOn =
    releaseDate && !Number.isNaN(releaseDate.getTime())
      ? formatDay(releaseDate, i18n.language)
      : null;
  const detail = [
    releasedOn ? t("settings.about.updates.released", { date: releasedOn }) : null,
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
    <UpdatesBlock>
      <div className="flex flex-col gap-3.5 text-sm">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 space-y-1">
            <p className="font-label">{headline}</p>
            <p className="text-text-muted">{detail}</p>
            {error ? (
              <p className="text-danger" role="alert">
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
              variant="outline"
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
          <div className="space-y-1 rounded-md bg-surface-sunken px-3 py-2">
            <p className="text-xs font-semibold uppercase tracking-[0.04em] text-text-muted">
              {t("settings.about.updates.whatsNew")}
            </p>
            <ul className="list-disc space-y-0.5 pl-4 text-sm leading-[1.6] text-text">
              {notes.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="flex items-center justify-between gap-4 border-t border-border-subtle pt-3.5">
          <div className="space-y-0.5">
            <p className="font-label">{t("settings.about.updates.auto")}</p>
            <p className="text-text-muted">{t("settings.about.updates.autoHelp")}</p>
          </div>
          <Switch
            checked={status?.autoCheck ?? true}
            disabled={!status}
            onCheckedChange={(checked) => void setAutoCheck(checked)}
            aria-label={t("settings.about.updates.auto")}
          />
        </div>
      </div>
    </UpdatesBlock>
  );
}

/** The Updates section: its title, then one hairline-topped body (an ordinary section, not a card). */
function UpdatesBlock({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-md font-semibold text-text">{t("settings.about.updates.title")}</h2>
      <div className="border-t border-border-subtle pt-3">{children}</div>
    </section>
  );
}
