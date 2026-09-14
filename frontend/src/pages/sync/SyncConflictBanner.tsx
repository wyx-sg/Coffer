// frontend/src/pages/sync/SyncConflictBanner.tsx
//
// A conflict blocks convergence on BOTH machines until it is resolved (spec
// vault-sync `## Conflicts`), so it is a banner at the top of Status rather
// than a line in the round report.
//
// What the user needs is three things and no more: that nothing was touched,
// which paths disagree, and where the working tree holding them is — because
// the resolution is theirs to make with their own git tools, and the next
// round simply carries on from whatever they leave behind.
import { useTranslation } from "react-i18next";
import { GitMerge } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

interface Props {
  paths: string[];
  worktree: string | null;
}

export function SyncConflictBanner({ paths, worktree }: Props) {
  const { t } = useTranslation();

  return (
    <Alert
      className="border-status-warn/40 bg-status-warn/5"
      data-testid="sync-conflict-banner"
      role="alert"
    >
      <GitMerge className="size-4" aria-hidden />
      <AlertTitle>{t("sync.conflict.title")}</AlertTitle>
      <AlertDescription className="space-y-3">
        <p className="text-muted-foreground">{t("sync.conflict.body")}</p>

        <div className="space-y-1">
          <p className="font-medium">{t("sync.conflict.paths")}</p>
          <ul className="space-y-0.5">
            {paths.map((path) => (
              <li key={path} className="font-mono text-xs">
                {path}
              </li>
            ))}
          </ul>
        </div>

        <p className="text-muted-foreground">{t("sync.conflict.resolve")}</p>
        {worktree ? (
          <p className="text-xs text-muted-foreground">
            {t("sync.conflict.worktree", { path: worktree })}
          </p>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}
