// src/components/DaemonOfflineBanner.tsx — the daemon's connection states in the workspace: the reconnecting bar, the offline state, the version warning.
//
// Boards 1.1.18 (reconnecting), 1.1.19 (offline), 1.1.12 (update) and the
// behaviour sheet (1.1.04, "Daemon connection"). Both are drawn in line, at the top of the workspace, never
// floating over the sidebar:
//
//   - Reconnecting — for the first seconds after the daemon stops answering,
//     the page stays, dimmed and inert, under a warning bar that counts the
//     attempts and offers Retry now. Nothing the user typed is lost.
//   - Offline — after that, the page makes way for one screen that says the
//     daemon isn't running and names the recovery the host can offer (spec
//     web-ui "Show a self-clearing offline banner"): in the desktop shell a
//     Start daemon control, because the shell can spawn one. Both hosts show
//     the `coffer daemon start` command with a Copy button ("Or start it from
//     a terminal"), and a footer line with the next check and the last reply.
//     The daemon log is read without the daemon: the desktop shell opens the
//     file in the system viewer (Open daemon log, a shell command), a browser
//     gets the `coffer log daemon` command to copy. It clears itself as soon as the daemon answers again.
//   - Version skew (desktop only) — the daemon answers, but an earlier app
//     version left it running: a warning bar with the shell's Restart.
//
// The phase comes from `useDaemonConnectionDriver` (shell/daemonConnection),
// which Layout mounts once; these components only render it.
import { useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Clock, Play, Power, RotateCw } from "lucide-react";

import { CopyableCommand } from "@/components/settings/CopyableCommand";
import { Button } from "@/components/ui/button";
import type { DaemonConnection } from "@/components/shell/daemonConnection";
import { ApiError } from "@/lib/api/errors";
import { useDaemonOutOfDate, useDaemonStatus, useRestartDaemon } from "@/lib/hooks/useDaemon";
import { isTauri, shellInvoke } from "@/lib/tauri";

/** A reply time as the clock reads it ("14:02"). */
function clockTime(ms: number): string {
  return new Date(ms).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** Seconds until `at`, re-read every second while mounted. */
function useSecondsUntil(at: number | null): number | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (at === null) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [at]);
  return at === null ? null : Math.max(0, Math.ceil((at - now) / 1000));
}

function restartMessage(error: unknown): string | null {
  if (!error) return null;
  return error instanceof Error ? error.message : String(error);
}

interface Props {
  connection: DaemonConnection;
  /** Probe again now. */
  onRetry: () => void;
}

/** The bar over the page: reconnecting, or (desktop) a daemon from another app version. */
export function DaemonStatusBar({ connection, onRetry }: Props) {
  const { t } = useTranslation();
  const status = useDaemonStatus();
  const { data: outOfDate } = useDaemonOutOfDate(status.data?.version);
  const restart = useRestartDaemon();
  const seconds = useSecondsUntil(
    connection.phase === "reconnecting" ? connection.nextRetryAt : null,
  );

  if (status.isError && connection.phase === "reconnecting") {
    return (
      <div
        role="status"
        data-testid="daemon-reconnecting"
        className="flex h-10 shrink-0 items-center gap-2.5 border-b border-border bg-warning-soft px-8"
      >
        {/* A partial ring, held still: the bar says "trying", the countdown is the motion. */}
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
          className="size-3.5 shrink-0 text-warning"
        >
          <path d="M12 3a9 9 0 1 0 9 9" />
        </svg>
        <span className="shrink-0 text-sm font-label text-text">
          {connection.lastReplyAt === null
            ? t("daemon.reconnect.connectingTitle")
            : t("daemon.reconnect.title")}
        </span>
        <span className="min-w-0 truncate text-xs text-text-muted">
          {t("daemon.reconnect.detail", { attempt: connection.attempt, seconds: seconds ?? 0 })}
        </span>
        <Button size="sm" variant="outline" className="ml-auto" onClick={onRetry}>
          {t("daemon.reconnect.retryNow")}
        </Button>
      </div>
    );
  }

  if (!status.isError && outOfDate === true) {
    return (
      <div
        role="status"
        data-testid="daemon-banner"
        data-banner-code="DAEMON_OUT_OF_DATE"
        className="flex min-h-10 shrink-0 flex-wrap items-center gap-2.5 border-b border-border bg-warning-soft px-8 py-1.5"
      >
        <span className="shrink-0 text-sm font-label text-text">
          {t("daemon.offline.outOfDateTitle")}
        </span>
        <span className="min-w-0 flex-1 text-xs text-text-muted">
          {t("daemon.offline.outOfDateBody")}
        </span>
        {isTauri() ? (
          <Button
            size="sm"
            variant="outline"
            loading={restart.isPending}
            onClick={() => restart.mutate()}
            data-testid="daemon-banner-restart"
          >
            <RotateCw aria-hidden />
            {restart.isPending ? t("daemon.offline.restarting") : t("daemon.offline.restart")}
          </Button>
        ) : null}
        {restart.error ? (
          <span className="w-full text-xs text-danger">{restartMessage(restart.error)}</span>
        ) : null}
      </div>
    );
  }

  return null;
}

/** The screen that takes the page's place while the daemon cannot be reached. */
export function DaemonOfflineState({ connection, onRetry }: Props) {
  const { t } = useTranslation();
  const status = useDaemonStatus();
  const restart = useRestartDaemon();
  const [logError, setLogError] = useState<string | null>(null);
  const seconds = useSecondsUntil(connection.nextRetryAt);
  const inShell = isTauri();

  const code = status.error instanceof ApiError ? status.error.code : "DAEMON_OFFLINE";
  // The last port the daemon answered on, else the one this page was served from.
  const port = status.data?.port ?? (Number(window.location.port) || null);
  const lastReply = connection.lastReplyAt;
  const restartError = restartMessage(restart.error);
  const timing = [
    seconds !== null ? t("daemon.offlineState.checkingIn", { seconds }) : null,
    lastReply !== null ? t("daemon.offlineState.lastReply", { time: clockTime(lastReply) }) : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const openLog = () => {
    setLogError(null);
    shellInvoke<void>("show_daemon_log").catch((e: unknown) => setLogError(restartMessage(e)));
  };

  return (
    <div
      className="flex min-h-full flex-1 items-center justify-center p-8"
      data-testid="daemon-banner"
      data-banner-code={code}
      role="alert"
    >
      <div className="flex w-[460px] max-w-full flex-col items-center gap-5 text-center">
        <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
          <Power className="size-[22px]" strokeWidth={1.75} aria-hidden />
        </span>
        <div className="flex flex-col gap-1.5">
          <h1 className="text-lg font-bold tracking-tight text-text">
            {t("daemon.offlineState.title")}
          </h1>
          <p className="text-sm leading-normal text-text-muted">
            {port ? (
              <Trans
                i18nKey="daemon.offlineState.body"
                values={{ address: `127.0.0.1:${port}` }}
                components={{ mono: <span className="font-mono text-xs" /> }}
              />
            ) : (
              t("daemon.offlineState.bodyNoAddress")
            )}
          </p>
        </div>
        <div className="flex gap-2">
          {inShell ? (
            <Button
              size="lg"
              loading={restart.isPending}
              onClick={() => restart.mutate()}
              data-testid="daemon-banner-restart"
            >
              <Play aria-hidden />
              {restart.isPending
                ? t("daemon.offlineState.starting")
                : t("daemon.offlineState.start")}
            </Button>
          ) : null}
          <Button size="lg" variant="outline" onClick={onRetry}>
            <RotateCw aria-hidden />
            {t("daemon.offlineState.retry")}
          </Button>
        </div>
        {restartError ? <p className="text-xs text-danger">{restartError}</p> : null}
        {/* The command works in both hosts (a browser cannot start the daemon
            that serves it); the retries clear this screen once it answers. */}
        <div className="flex w-full flex-col gap-2 text-left">
          <span className="text-xs text-text-muted">{t("daemon.offline.webRestartHint")}</span>
          <CopyableCommand command="coffer daemon start" />
        </div>
        {/* The Activity page's Daemon log tab needs the daemon, so the log is
            read around it: the shell opens the file, a browser reads it from a terminal. */}
        {inShell ? null : (
          <div className="flex w-full flex-col gap-2 text-left">
            <span className="text-xs text-text-muted">{t("daemon.offlineState.logHint")}</span>
            <CopyableCommand command="coffer log daemon" />
          </div>
        )}
        <p className="inline-flex flex-wrap items-center justify-center gap-x-2 text-xs text-text-muted">
          <Clock className="size-[13px] shrink-0" strokeWidth={1.75} aria-hidden />
          {timing}
          {inShell ? (
            <>
              {timing ? " ·" : null}
              <button
                type="button"
                onClick={openLog}
                className="font-label text-accent-text hover:underline"
              >
                {t("daemon.offlineState.openLog")}
              </button>
            </>
          ) : null}
        </p>
        {logError ? <p className="text-xs text-danger">{logError}</p> : null}
      </div>
    </div>
  );
}
