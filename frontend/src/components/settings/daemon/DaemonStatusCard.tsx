// src/components/settings/daemon/DaemonStatusCard.tsx — Settings › Daemon's status card and the host's restart (design 6.2.11 / 6.2.12).
//
// Spec web-ui "Show and manage the daemon on Settings → Daemon": the state and
// the address it answers on, then one line — how long it has been up, its pid
// and how many agents carry Coffer's connection — all from the status probe
// (the version is on About and in the sidebar footer). A Restart control in
// both hosts: the shell's restart in the desktop shell, the daemon's own
// restart in a browser (`useRestartDaemon`; the page then reloads from the new
// daemon). While the daemon cannot be reached the card reads offline and names
// the host's recovery: nothing is running that could restart itself, so a
// browser names `coffer daemon start`. No stop or shutdown control, anywhere.
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { Power, RotateCw } from "lucide-react";

import { CopyableCommand } from "@/components/settings/CopyableCommand";
import { StatusDot } from "@/components/status/StatusDot";
import { STATUS_TONE, type StatusTone } from "@/components/status/statusTone";
import type { DaemonFooterState } from "@/components/shell/useDaemonFooterState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { components } from "@/lib/api/types";
import { restartErrorText } from "@/lib/daemonRestart";
import { useRestartDaemon } from "@/lib/hooks/useDaemon";
import { toneClass } from "@/lib/statusColors";
import { splitDuration } from "@/lib/usage/format";
import { cn } from "@/lib/utils";

type DaemonStatus = components["schemas"]["DaemonStatusOut"];

const TONE: Record<DaemonFooterState["kind"], StatusTone> = {
  running: "ok",
  connecting: "off",
  stopping: "warn",
  reconnecting: "warn",
  offline: "err",
};

/** "Up 3 days" — the largest whole unit since `startedAt`. */
function uptime(t: TFunction, startedAt: string, now: number): string {
  const { days, hours, minutes } = splitDuration(now - new Date(startedAt).getTime());
  if (days > 0) return t("settings.daemonTab.upDays", { count: days });
  if (hours > 0) return t("settings.daemonTab.upHours", { count: hours });
  if (minutes > 0) return t("settings.daemonTab.upMinutes", { count: minutes });
  return t("settings.daemonTab.upJustNow");
}

/** "Up 3 days · pid 51233 · 2 agents connected" — the parts the probe answered. */
function statusLine(t: TFunction, status: DaemonStatus, now: number): string {
  const parts = [
    uptime(t, status.started_at, now),
    t("settings.daemonTab.pid", { pid: status.pid }),
  ];
  if (status.connected_agents != null) {
    parts.push(t("settings.daemonTab.agentsConnected", { count: status.connected_agents }));
  }
  return parts.join(" · ");
}

interface Props {
  state: DaemonFooterState;
  status: DaemonStatus | undefined;
  /** In the desktop shell (secret-supplier module, `lib/tauri.ts`). */
  inShell: boolean;
}

/** The status card; loading keeps its shape over skeleton rows. */
export function DaemonStatusCard({ state, status, inShell }: Props) {
  const { t } = useTranslation();
  const restart = useRestartDaemon();

  if (state.kind === "connecting") {
    return (
      <div
        className="flex flex-col gap-2 rounded-xl border border-border-subtle p-4"
        data-testid="settings-daemon-status-loading"
      >
        <Skeleton className="h-5 w-56" />
        <Skeleton className="h-4 w-72" />
      </div>
    );
  }

  const title =
    state.kind === "running"
      ? t("settings.daemonTab.runningOn", { port: state.port })
      : t(`settings.daemonTab.state.${state.kind}`);
  const restartButton = (
    <Button variant="outline" onClick={() => restart.mutate()} disabled={restart.isPending}>
      <RotateCw aria-hidden />{" "}
      {restart.isPending ? t("daemon.offline.restarting") : t("settings.daemonTab.restart")}
    </Button>
  );

  return (
    <div
      className="flex flex-col gap-3 rounded-xl border border-border-subtle p-4"
      data-testid="settings-daemon-status"
    >
      <div className="flex flex-wrap items-center gap-3">
        <span
          aria-hidden
          className={cn(
            "inline-flex size-8 shrink-0 items-center justify-center rounded-lg border border-border-subtle",
            toneClass(STATUS_TONE[TONE[state.kind]]),
          )}
        >
          <Power className="size-4" strokeWidth={1.75} />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <p className="flex items-center gap-2 text-md font-semibold text-text">
            {state.kind === "running" ? null : <StatusDot tone={TONE[state.kind]} />}
            {title}
          </p>
          {state.kind === "offline" ? (
            <p className="text-xs text-text-muted">
              {inShell
                ? t("settings.daemonTab.offlineShell")
                : t("settings.daemonTab.offlineBrowser")}
            </p>
          ) : status ? (
            <p
              className="text-xs text-text-muted"
              data-testid="settings-daemon-status-line"
              data-visual-volatile
            >
              {statusLine(t, status, Date.now())}
            </p>
          ) : null}
        </div>
        {inShell || state.kind !== "offline" ? restartButton : null}
      </div>

      {state.kind === "offline" && !inShell ? (
        <CopyableCommand command="coffer daemon start" />
      ) : null}

      {restart.error ? (
        <p className="text-xs text-danger" role="alert">
          {restartErrorText(t, restart.error)}
        </p>
      ) : null}
    </div>
  );
}
