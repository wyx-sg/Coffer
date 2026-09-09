import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AlertCircle, Loader2 } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

/**
 * Shown above every page when /api/v1/daemon/status fails. Two flavours:
 *
 *   - UNAUTHENTICATED / DAEMON_NOT_READY (envelope codes from
 *     surfaces/http/errors.py): the daemon is reachable but the token is
 *     missing — surface the "daemon not ready" copy instead of a generic
 *     error, because the user's next action is usually "start the daemon".
 *   - Other errors: original "daemon offline" treatment.
 *
 * Recovery affordance: a Retry button that re-checks status once the user has
 * brought the daemon back up, plus the terminal command that does so. Keeping
 * this opinionated avoids the "generic unexpected error on every page" symptom
 * we hit pre-redesign whenever ~/.coffer/daemon.json was absent.
 */
export function DaemonOfflineBanner() {
  const { t } = useTranslation();
  const { error, isError } = useDaemonStatus();
  const qc = useQueryClient();

  // Recovery: a *soft* retry that refetches the daemon status (and every
  // cached query) in place. NOT window.location.reload() — a hard reload
  // navigates to the page host (the Vite dev server, or the daemon-served
  // bundle); if that host is itself down the browser shows ERR_CONNECTION_REFUSED
  // and the whole app goes blank. Refetching recovers when the daemon returns
  // and otherwise just leaves the banner up.
  const reload = useMutation({
    mutationFn: () => qc.invalidateQueries(),
  });

  if (!isError) return null;

  const code = error instanceof ApiError ? error.code : "DAEMON_OFFLINE";
  const isAuthGap = code === "UNAUTHENTICATED" || code === "DAEMON_NOT_READY";

  // Floats over the whole app (above the sidebar too): a fixed, top-centered
  // card that doesn't take layout space, so page content stays put underneath.
  // pointer-events-none on the wrapper lets clicks pass through the empty gutter;
  // the card itself re-enables them.
  return (
    <div className="pointer-events-none fixed inset-x-0 top-4 z-50 flex justify-center px-4">
      <Alert
        variant="destructive"
        className="pointer-events-auto w-full max-w-xl border-status-warn/40 bg-card text-foreground shadow-lg"
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
          <div className="space-y-2">
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
            {/* The browser can't kill/respawn the daemon — Retry only re-checks
                the connection. Tell the user how to actually bring it back. */}
            <p className="text-xs text-foreground/60">
              {t("daemon.offline.webRestartHint")}{" "}
              <code className="rounded bg-muted px-1 py-0.5 font-mono">coffer daemon start</code>
            </p>
          </div>
        </AlertDescription>
      </Alert>
    </div>
  );
}
