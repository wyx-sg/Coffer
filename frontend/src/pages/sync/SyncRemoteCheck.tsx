// frontend/src/pages/sync/SyncRemoteCheck.tsx
//
// What Check repository found when it is not something setup can go on with:
// a repository that is not a Coffer vault, one that cannot be reached, a
// refused sign-in, or a check that failed — each in a plain sentence, with
// git's own words (already scrubbed by the daemon) under it. An empty
// repository and a vault move setup on instead (see SyncSetup).
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";

import { translateApiError } from "@/lib/api/errors";
import type { RemoteCheck } from "@/lib/api/sync";

export function SyncRemoteCheck({ result, error }: { result?: RemoteCheck; error?: unknown }) {
  const { t } = useTranslation();
  if (!result && !error) return null;
  if (result && (result.result === "empty" || result.result === "vault")) return null;

  return (
    <div
      className="flex items-start gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5"
      role="alert"
      data-testid="sync-remote-check"
    >
      <AlertTriangle className="mt-px size-[15px] shrink-0 text-danger" aria-hidden />
      <div className="flex min-w-0 flex-col gap-1">
        <span className="text-sm font-label text-text">
          {result
            ? t(`sync.setup.check.${result.result}`, { layout: result.layout ?? "?" })
            : t("sync.setup.check.failed")}
        </span>
        {result?.detail || error ? (
          <span className="break-words font-mono text-xs text-text-muted">
            {result?.detail ?? translateApiError(t, error)}
          </span>
        ) : null}
      </div>
    </div>
  );
}
