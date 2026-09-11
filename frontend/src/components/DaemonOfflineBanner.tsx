import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

/**
 * Shown above every page when /api/v1/daemon/status fails. Two flavours:
 *
 *   - UNAUTHENTICATED / DAEMON_NOT_READY (envelope codes from
 *     surfaces/http/errors.py): the daemon is reachable but the token is
 *     missing — surface the "daemon not ready" copy instead of a generic
 *     error, because the user's next action is usually "start the daemon".
 *   - Other errors: original "daemon offline" treatment.
 *
 * Recovery affordance: the terminal command that brings the daemon back. There
 * is no Retry button — the browser cannot restart the daemon, and the status
 * query polls every 30s, so the banner clears itself once the daemon returns;
 * a button that only shortened that wait was one more thing to explain. Keeping
 * this opinionated avoids the "generic unexpected error on every page" symptom
 * we hit pre-redesign whenever ~/.coffer/daemon.json was absent.
 */
export function DaemonOfflineBanner() {
  const { t } = useTranslation();
  const { error, isError } = useDaemonStatus();
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
            {/* The browser can't kill/respawn the daemon. Tell the user how to
                actually bring it back; the 30s status poll clears the banner. */}
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
