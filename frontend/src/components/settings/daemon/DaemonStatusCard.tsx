// src/components/settings/daemon/DaemonStatusCard.tsx — Settings › Daemon's status card and the host's restart (design 6.2.11 / 6.2.12).
//
// Spec web-ui "Show and manage the daemon on Settings → Daemon": the state,
// version, release channel, port, start time and executable, all from the
// status probe; in the desktop shell a Restart control that runs the shell's
// restart, in a browser the `coffer daemon restart` command to copy, since a
// page the daemon serves cannot start the daemon that replaces it. While the
// daemon cannot be reached the card reads offline and names the host's
// recovery. No stop or shutdown control, anywhere.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { RotateCw } from "lucide-react";

import { CopyableCommand } from "@/components/settings/CopyableCommand";
import { StatusDot } from "@/components/status/StatusDot";
import type { StatusTone } from "@/components/status/statusTone";
import type { DaemonFooterState } from "@/components/shell/useDaemonFooterState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import { useRestartDaemon } from "@/lib/hooks/useDaemon";
import { formatDateTime } from "@/lib/utils";

type DaemonStatus = components["schemas"]["DaemonStatusOut"];

const TONE: Record<DaemonFooterState["kind"], StatusTone> = {
  running: "ok",
  connecting: "off",
  stopping: "warn",
  offline: "err",
};

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3 text-xs">
      <dt className="w-24 shrink-0 text-text-muted">{label}</dt>
      <dd className="min-w-0 break-all text-text">{children}</dd>
    </div>
  );
}

interface Props {
  state: DaemonFooterState;
  status: DaemonStatus | undefined;
  /** In the desktop shell (credential-supplier module, `lib/tauri.ts`). */
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
        <Skeleton className="h-4 w-64" />
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
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="flex items-center gap-2 text-sm font-semibold text-text">
            <StatusDot tone={TONE[state.kind]} />
            {title}
          </p>
          {state.kind === "offline" ? (
            <p className="text-xs text-text-muted">
              {inShell
                ? t("settings.daemonTab.offlineShell")
                : t("settings.daemonTab.offlineBrowser")}
            </p>
          ) : null}
        </div>
        {inShell ? restartButton : null}
      </div>

      {state.kind === "offline" && !inShell ? (
        <CopyableCommand command="coffer daemon start" />
      ) : null}

      {status && state.kind !== "offline" ? (
        <dl className="flex flex-col gap-1">
          <Fact label={t("settings.daemonTab.version")}>{status.version}</Fact>
          <Fact label={t("settings.daemonTab.channel")}>{status.channel}</Fact>
          <Fact label={t("settings.daemonTab.startedAt")}>{formatDateTime(status.started_at)}</Fact>
          <Fact label={t("settings.daemonTab.executable")}>
            <span className="font-mono" data-visual-volatile>
              {status.executable}
            </span>
          </Fact>
        </dl>
      ) : null}

      {!inShell && state.kind !== "offline" ? (
        <div className="flex flex-col gap-1.5">
          <p className="text-xs text-text-muted">{t("settings.daemonTab.browserRestart")}</p>
          <CopyableCommand command="coffer daemon restart" />
        </div>
      ) : null}

      {restart.error ? (
        <p className="text-xs text-danger" role="alert">
          {translateApiError(t, restart.error)}
        </p>
      ) : null}
    </div>
  );
}
