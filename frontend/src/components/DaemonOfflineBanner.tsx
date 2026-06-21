import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AlertCircle, Loader2 } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { resetApiClient } from "@/lib/api/client";
import { setDaemonConnection } from "@/lib/auth";
import { useDaemonOutOfDate, useDaemonStatus } from "@/lib/hooks/useDaemon";
import { Button } from "@/components/ui/button";
import { getDaemonInfo, isTauri, restartDaemon } from "@/lib/tauri";

/**
 * Shown above every page when /api/v1/daemon/status fails. Two flavours:
 *
 *   - UNAUTHENTICATED / DAEMON_NOT_READY (envelope codes from
 *     surfaces/http/errors.py): the daemon is reachable but the token is
 *     missing — surface the "daemon not ready" copy instead of a generic
 *     error, because the user's next action is usually "start the daemon".
 *   - Other errors: original "daemon offline" treatment.
 *
 * Recovery affordance: the desktop app offers a Restart button (Tauri can
 * relaunch the daemon); on the web it's a Reload button that re-checks status
 * once the user has brought the daemon back up. Keeping this opinionated
 * avoids the "generic unexpected error on every page" symptom we hit
 * pre-redesign whenever ~/.coffer/daemon.json was absent.
 */
export function DaemonOfflineBanner() {
  const { t } = useTranslation();
  const { data: status, error, isError } = useDaemonStatus();
  // Version skew (P2): the daemon answers fine but reports a different version
  // than this app build expects — i.e. the app reused a stale daemon a previous
  // app version left detached. Surface the same restart affordance; don't
  // auto-kill it.
  const { data: isOutOfDate } = useDaemonOutOfDate(status?.version);
  const qc = useQueryClient();
  // useMutation owns the in-flight / error state and dedups double-clicks,
  // so the banner doesn't hand-roll a restarting/restartError pair.
  const restart = useMutation({
    mutationFn: async () => {
      const result = await restartDaemon();
      // The daemon mints a fresh token on every start, so the credentials
      // injected at launch are now revoked. Re-fetch the connection info
      // from the Tauri shell (get_daemon_info waits for the new daemon to
      // publish daemon.json and listen) and swap it in before any query
      // refetches — otherwise every request 401s until the app relaunches.
      try {
        const info = await getDaemonInfo();
        setDaemonConnection(info.baseUrl, info.token);
        resetApiClient();
      } catch (e) {
        // Distinct failure: the daemon DID restart but we couldn't fetch
        // its new credentials — tell the user to relaunch rather than
        // implying the restart itself failed.
        const message = e instanceof Error ? e.message : String(e);
        throw new Error(t("daemon.offline.reconnectFailed", { message }));
      }
      return result;
    },
    // The token changed, so every cached query (not just daemon/status)
    // was fetched with the revoked credentials — refetch the whole cache
    // so the app recovers in place.
    onSuccess: () => qc.invalidateQueries(),
  });

  // Web recovery: a *soft* retry that refetches the daemon status (and every
  // cached query) in place. NOT window.location.reload() — a hard reload
  // navigates to the page host (the Vite dev server, or the daemon-served
  // bundle); if that host is itself down the browser shows ERR_CONNECTION_REFUSED
  // and the whole app goes blank. Refetching recovers when the daemon returns
  // and otherwise just leaves the banner up.
  const reload = useMutation({
    mutationFn: () => qc.invalidateQueries(),
  });

  // The daemon is out of date when it's reachable (no query error) but reports
  // a stale version. Skew only matters while the daemon is actually answering.
  const isStale = !isError && isOutOfDate === true;
  if (!isError && !isStale) return null;

  const code = error instanceof ApiError ? error.code : "DAEMON_OFFLINE";
  const isAuthGap = code === "UNAUTHENTICATED" || code === "DAEMON_NOT_READY";
  const restartError = restart.error
    ? restart.error instanceof Error
      ? restart.error.message
      : String(restart.error)
    : null;

  const title = isStale
    ? t("daemon.offline.outOfDateTitle")
    : isAuthGap
      ? t("daemon.offline.notReadyTitle")
      : t("daemon.offline.title");
  const body = isStale
    ? t("daemon.offline.outOfDateBody")
    : isAuthGap
      ? t("daemon.offline.notReadyBody")
      : t("daemon.offline.body");
  const errorSuffix =
    !isStale && !isAuthGap && error instanceof Error ? ` (${error.message})` : null;

  // A full-width status strip across the very top of the app, NOT a floating
  // card. Layout renders it above the sidebar + content row, so it pushes the
  // app down instead of overlaying it; returning null when healthy means it
  // reserves no space then. The icon + message run on the left and the recovery
  // action(s) on the right, wrapping to a second line only when space is tight.
  return (
    <div
      role="alert"
      className="border-b border-status-warn/40 bg-card text-foreground shadow-sm"
      data-testid="daemon-banner"
      data-banner-code={isStale ? "DAEMON_OUT_OF_DATE" : code}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2.5">
        <AlertCircle className="size-4 shrink-0 text-status-warn" />
        <div className="min-w-0 flex-1 text-sm">
          <span className="font-serif font-medium">{title}</span>
          <span className="ml-2 text-foreground/80">
            {body}
            {errorSuffix}
          </span>
          {!isTauri() ? (
            // The browser can't kill/respawn the daemon — Retry only re-checks
            // the connection. Tell the user how to actually bring it back.
            <span className="ml-2 text-foreground/60">
              {t("daemon.offline.webRestartHint")}{" "}
              <code className="rounded bg-muted px-1 py-0.5 font-mono">coffer daemon start</code>
            </span>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {isTauri() ? (
            <>
              {restartError ? (
                <span className="text-xs text-destructive">{restartError}</span>
              ) : null}
              <Button
                size="sm"
                variant="outline"
                onClick={() => restart.mutate()}
                disabled={restart.isPending}
              >
                {restart.isPending ? (
                  <>
                    <Loader2 className="mr-2 size-4 animate-spin" />
                    {t("daemon.offline.restarting")}
                  </>
                ) : (
                  t("daemon.offline.restart")
                )}
              </Button>
            </>
          ) : (
            <Button
              size="sm"
              variant="outline"
              onClick={() => reload.mutate()}
              disabled={reload.isPending}
              data-testid="daemon-banner-reload"
            >
              {reload.isPending ? (
                <>
                  <Loader2 className="mr-2 size-4 animate-spin" />
                  {t("daemon.offline.retrying")}
                </>
              ) : (
                t("daemon.offline.retry")
              )}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
