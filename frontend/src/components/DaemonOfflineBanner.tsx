import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AlertCircle, Loader2 } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { isTauri, restartDaemon } from "@/lib/tauri";

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
  const { error, isError } = useDaemonStatus();
  const qc = useQueryClient();
  // useMutation owns the in-flight / error state and dedups double-clicks,
  // so the banner doesn't hand-roll a restarting/restartError pair. On a
  // successful restart, re-check status immediately so the banner clears
  // without waiting for the 30s poll.
  const restart = useMutation({
    mutationFn: () => restartDaemon(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["daemon", "status"] }),
  });

  if (!isError) return null;

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
      data-banner-code={code}
    >
      <AlertCircle className="size-4 text-status-warn" />
      <AlertTitle className="font-serif text-base">
        {isAuthGap ? t("daemon.offline.notReadyTitle") : t("daemon.offline.title")}
      </AlertTitle>
      <AlertDescription>
        <p className="mb-3 text-foreground/80">
          {isAuthGap ? t("daemon.offline.notReadyBody") : t("daemon.offline.body")}
          {!isAuthGap && error instanceof Error ? ` (${error.message})` : null}
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
