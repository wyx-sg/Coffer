// frontend/src/pages/settings/BrowserUpdates.tsx
//
// Settings › About › Updates in a browser (spec web-ui "Check for and install
// updates on Settings › About"). A page the daemon serves cannot replace the
// application, so nothing here installs. A daemon running from the installer's
// binaries checks for releases itself (spec daemon "Check the installed
// binaries for a new release"): the section shows what it found, its Check for
// updates and its Check automatically switch, and `coffer update` to copy when
// a newer version is out. Any other daemon is updated by the desktop app. In
// both cases the upgrade can be handed to an agent.
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { CopyableCommand } from "@/components/settings/CopyableCommand";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import type { DaemonUpgrade } from "@/lib/api/daemon";
import { translateApiError } from "@/lib/api/errors";
import { useDaemonUpgrade, useDaemonUpgradeActions } from "@/lib/hooks/useDaemon";
import { formatClockOrMoment, formatDay } from "@/lib/time";

export function BrowserUpdates() {
  const { t } = useTranslation();
  const upgrade = useDaemonUpgrade(true);
  const data = upgrade.data;
  if (data?.checks) return <DaemonCheck upgrade={data} />;
  // An older daemon answers without the hand-off.
  const prompt = data?.handoff?.prompt;
  return (
    <div className="space-y-3 text-sm text-text-muted">
      <p>{t("settings.about.updates.browser")}</p>
      {prompt ? <AgentHandoff prompt={prompt} size="sm" /> : null}
    </div>
  );
}

function DaemonCheck({ upgrade }: { upgrade: DaemonUpgrade }) {
  const { t, i18n } = useTranslation();
  const { check, setAutoCheck } = useDaemonUpgradeActions();
  const offer = upgrade.available ?? null;
  const checking = check.isPending;
  const failed = Boolean(upgrade.last_error) || check.isError;
  const checkedAt = upgrade.checked_at ? new Date(upgrade.checked_at) : null;

  let headline: string;
  if (offer) headline = t("settings.about.updates.available", { version: offer.version });
  else if (failed) headline = t("settings.about.updates.failed");
  else if (checkedAt) headline = t("settings.about.updates.upToDate");
  else headline = t("settings.about.updates.notChecked");

  const released = offer?.published_at ? new Date(offer.published_at) : null;
  const detail = [
    released && !Number.isNaN(released.getTime())
      ? t("settings.about.updates.released", { date: formatDay(released, i18n.language) })
      : null,
    checkedAt
      ? t("settings.about.updates.lastChecked", {
          time: formatClockOrMoment(checkedAt, i18n.language, t),
        })
      : t("settings.about.updates.daemonNeverChecked"),
    offer ? t("settings.about.updates.commandHelp") : null,
  ]
    .filter(Boolean)
    .join(" ");
  const error = check.isError ? translateApiError(t, check.error) : upgrade.last_error;
  const notes = (offer?.notes ?? "")
    .split("\n")
    .map((line) => line.replace(/^\s*[-*·]\s*/, "").trim())
    .filter(Boolean);

  return (
    <div className="flex flex-col gap-3.5 text-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <p className="font-label">{headline}</p>
          <p className="text-text-muted">{detail}</p>
          {error ? (
            <p className="text-danger" role="alert">
              {error}
            </p>
          ) : null}
        </div>
        <Button size="sm" variant="outline" disabled={checking} onClick={() => check.mutate()}>
          <RefreshCw aria-hidden className={checking ? "animate-spin" : undefined} />
          {checking
            ? t("settings.about.updates.checking")
            : failed
              ? t("settings.about.updates.tryAgain")
              : t("settings.about.updates.check")}
        </Button>
      </div>

      {offer ? <CopyableCommand command="coffer update" /> : null}

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
          <p className="text-text-muted">{t("settings.about.updates.daemonAutoHelp")}</p>
        </div>
        <Switch
          checked={upgrade.auto_check}
          disabled={setAutoCheck.isPending}
          onCheckedChange={(checked) => setAutoCheck.mutate(checked)}
          aria-label={t("settings.about.updates.auto")}
        />
      </div>

      <AgentHandoff prompt={upgrade.handoff.prompt} size="sm" />
    </div>
  );
}
