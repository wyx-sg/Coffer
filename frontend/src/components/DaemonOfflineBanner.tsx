// src/components/DaemonOfflineBanner.tsx — the daemon's connection states in the workspace: the reconnecting bar, the offline state, the version warning.
//
// Boards 1.2.17 / 1.2.18 / 1.2.24 and the behaviour sheet (1.2.20, "Daemon
// connection"). Both are drawn in line, at the top of the workspace, never
// floating over the sidebar:
//
//   - Reconnecting — for the first seconds after the daemon stops answering,
//     the page stays, dimmed and inert, under a warning bar that counts the
//     attempts and offers Retry now. Nothing the user typed is lost.
//   - Offline — after that, the page makes way for one screen that says the
//     daemon isn't running and names the recovery the host can offer (spec
//     web-ui "Show a self-clearing offline banner"): in the desktop shell a
//     Start daemon control, because the shell can spawn one; in a browser the
//     `coffer daemon start` command, because a page the daemon serves cannot.
//     It clears itself as soon as the daemon answers again.
//   - Version skew (desktop only) — the daemon answers, but an earlier app
//     version left it running: a warning bar with the shell's Restart.
//
// The phase comes from `useDaemonConnectionDriver` (shell/daemonConnection),
// which Layout mounts once; these components only render it.
import { useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Clock, Loader2, Play, Power, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { DaemonConnection } from "@/components/shell/daemonConnection";
import { ApiError } from "@/lib/api/errors";
import { useDaemonOutOfDate, useDaemonStatus, useRestartDaemon } from "@/lib/hooks/useDaemon";
import { isTauri } from "@/lib/tauri";

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
        <Loader2
          className="size-3.5 shrink-0 animate-spin text-warning motion-reduce:animate-none"
          aria-hidden
        />
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
  const seconds = useSecondsUntil(connection.nextRetryAt);
  const inShell = isTauri();

  const code = status.error instanceof ApiError ? status.error.code : "DAEMON_OFFLINE";
  // The last port the daemon answered on, else the one this page was served from.
  const port = status.data?.port ?? (Number(window.location.port) || null);
  const lastReply = connection.lastReplyAt;
  const restartError = restartMessage(restart.error);

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
          <h1 className="text-lg font-semibold tracking-tight text-text">
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
        {inShell ? null : (
          // The browser cannot start the daemon that serves it; the command is
          // the recovery, and the retries clear this screen once it answers.
          <p className="text-xs text-text-muted">
            {t("daemon.offline.webRestartHint")}{" "}
            <code className="rounded-xs bg-surface-sunken px-1 py-0.5 font-mono text-text">
              coffer daemon start
            </code>
          </p>
        )}
        <p className="inline-flex items-center gap-2 text-xs text-text-muted">
          <Clock className="size-[13px] shrink-0" strokeWidth={1.75} aria-hidden />
          {[
            seconds !== null ? t("daemon.offlineState.checkingIn", { seconds }) : null,
            lastReply !== null
              ? t("daemon.offlineState.lastReply", { time: clockTime(lastReply) })
              : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </div>
    </div>
  );
}
