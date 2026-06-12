import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AlertCircle, Loader2 } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { resetApiClient } from "@/lib/api/client";
import { setDaemonConnection } from "@/lib/auth";
import { useDaemonOutOfDate, useDaemonStatus } from "@/lib/hooks/useDaemon";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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

  return (
    <Alert
      variant="destructive"
      className="mb-6 border-status-warn/40 bg-status-warn/5 text-foreground"
      data-testid="daemon-banner"
      data-banner-code={isStale ? "DAEMON_OUT_OF_DATE" : code}
    >
      <AlertCircle className="size-4 text-status-warn" />
      <AlertTitle className="font-serif text-base">
        {isStale
          ? t("daemon.offline.outOfDateTitle")
          : isAuthGap
            ? t("daemon.offline.notReadyTitle")
            : t("daemon.offline.title")}
      </AlertTitle>
      <AlertDescription>
        <p className="mb-3 text-foreground/80">
          {isStale
            ? t("daemon.offline.outOfDateBody")
            : isAuthGap
              ? t("daemon.offline.notReadyBody")
              : t("daemon.offline.body")}
          {!isStale && !isAuthGap && error instanceof Error ? ` (${error.message})` : null}
        </p>
        {isTauri() ? (
          <div className="space-y-2">
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
            {restartError ? <p className="text-xs text-destructive">{restartError}</p> : null}
          </div>
        ) : (
          <Button
            size="sm"
            variant="outline"
            onClick={() => window.location.reload()}
            data-testid="daemon-banner-reload"
          >
            {t("daemon.offline.reload")}
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}
