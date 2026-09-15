// src/components/DaemonOfflineBanner.tsx — floating banner when the daemon is offline, not ready, or out of date.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AlertCircle, Loader2 } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { useDaemonOutOfDate, useDaemonStatus } from "@/lib/hooks/useDaemon";
import { connectToShellDaemon, isTauri, restartDaemon } from "@/lib/tauri";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

/**
 * Shown above every page when /api/v1/daemon/status fails. Three flavours:
 *
 *   - UNAUTHENTICATED / DAEMON_NOT_READY (envelope codes from
 *     surfaces/http/errors.py): the daemon is reachable but the token is
 *     missing — surface the "daemon not ready" copy instead of a generic
 *     error, because the user's next action is usually "start the daemon".
 *   - Version skew: the daemon answers fine but reports a version this app
 *     build did not pair with — i.e. the desktop app found one an earlier
 *     version left detached. Desktop-only; see useDaemonOutOfDate.
 *   - Other errors: original "daemon offline" treatment.
 *
 * Recovery affordance, and why it differs by host. In a browser there is no
 * button: the browser cannot restart the daemon, and the status query polls
 * every 30s, so the banner clears itself once the daemon returns; a button that
 * only shortened that wait was one more thing to explain. What the user needs
 * is the command, so that is all this shows. The desktop shell is the exception
 * the design ADR carves out — its page is a local asset that is already
 * rendered with no daemon behind it, and the shell *can* spawn one, so there
 * the button is the recovery rather than a shortcut to waiting for it.
 * Keeping this opinionated avoids the "generic unexpected error on every page"
 * symptom we hit pre-redesign whenever ~/.coffer/daemon.json was absent.
 */
export function DaemonOfflineBanner() {
  const { t } = useTranslation();
  const { data: status, error, isError } = useDaemonStatus();
  const { data: isOutOfDate } = useDaemonOutOfDate(status?.version);
  const qc = useQueryClient();
  // useMutation owns the in-flight / error state and dedups double-clicks,
  // so the banner doesn't hand-roll a restarting/restartError pair.
  const restart = useMutation({
    mutationFn: async () => {
      const result = await restartDaemon();
      // The daemon mints a fresh token on every start, so the credentials the
      // shell handed over at launch are now revoked. Re-run the handshake
      // (get_daemon_info waits for the new daemon to publish daemon.json and
      // listen) and swap the connection in before anything refetches —
      // otherwise every request 401s until the app is relaunched.
      try {
        await connectToShellDaemon();
      } catch (e) {
        // Distinct failure: the daemon DID restart but we couldn't fetch its
        // new credentials — tell the user to relaunch rather than implying the
        // restart itself failed.
        const message = e instanceof Error ? e.message : String(e);
        throw new Error(t("daemon.offline.reconnectFailed", { message }));
      }
      return result;
    },
    // The token changed, so every cached query (not just daemon/status) was
    // fetched with the revoked credentials — refetch the whole cache so the
    // app recovers in place.
    onSuccess: () => qc.invalidateQueries(),
  });

  // Skew only matters while the daemon is actually answering; an offline
  // daemon has a louder problem and the same recovery.
  const isStale = !isError && isOutOfDate === true;
  if (!isError && !isStale) return null;

  const code = error instanceof ApiError ? error.code : "DAEMON_OFFLINE";
  const isAuthGap = code === "UNAUTHENTICATED" || code === "DAEMON_NOT_READY";
  const restartError = restart.error
    ? restart.error instanceof Error
      ? restart.error.message
      : String(restart.error)
    : null;

  // Floats over the whole app (above the sidebar too): a fixed, top-centered
  // card that doesn't take layout space, so page content stays put underneath.
  // pointer-events-none on the wrapper lets clicks pass through the empty gutter;
  // the card itself re-enables them.
  return (
    <div className="pointer-events-none fixed inset-x-0 top-4 z-50 flex justify-center px-4">
      <Alert
        variant="warning"
        className="pointer-events-auto w-full max-w-xl shadow-lg"
        data-testid="daemon-banner"
        data-banner-code={isStale ? "DAEMON_OUT_OF_DATE" : code}
      >
        <AlertCircle className="size-4" />
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
          </p>
          {isTauri() ? (
            <div className="space-y-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => restart.mutate()}
                disabled={restart.isPending}
                data-testid="daemon-banner-restart"
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
            <div className="space-y-2">
              {/* The browser can't kill/respawn the daemon. Tell the user how to
                  actually bring it back; the 30s status poll clears the banner. */}
              <p className="text-xs text-foreground/60">
                {t("daemon.offline.webRestartHint")}{" "}
                <code className="rounded-sm bg-muted px-1 py-0.5 font-mono">coffer daemon start</code>
              </p>
            </div>
          )}
        </AlertDescription>
      </Alert>
    </div>
  );
}
