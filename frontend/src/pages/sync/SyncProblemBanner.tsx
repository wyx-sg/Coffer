// frontend/src/pages/sync/SyncProblemBanner.tsx
//
// Why sync is not working right now, in the words that tell a person what to
// do: a refused sign-in names the credential reference it tried (the secret
// itself never reaches the page), a cloud-synced folder names the vault's path
// and the tool that syncs it, and every kind carries git's own message.
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { SyncProblem } from "@/lib/api/sync";
import { formatDateTime } from "@/lib/utils";

interface Props {
  problem: SyncProblem;
  vaultPath: string;
  synchroniser: string | null;
}

export function SyncProblemBanner({ problem, vaultPath, synchroniser }: Props) {
  const { t } = useTranslation();
  return (
    <Alert variant="error" role="alert" data-testid="sync-problem">
      <AlertTriangle aria-hidden />
      <AlertTitle>{t(`sync.problem.${problem.kind}.title`)}</AlertTitle>
      <AlertDescription className="space-y-1">
        <p>
          {t(`sync.problem.${problem.kind}.body`, {
            ref: problem.credential_ref ?? t("sync.problem.noCredential"),
            path: vaultPath,
            tool: synchroniser ?? t("sync.problem.cloudTool"),
          })}
        </p>
        {problem.message ? <p className="font-mono">{problem.message}</p> : null}
        {problem.since ? (
          <p>{t("sync.problem.since", { when: formatDateTime(problem.since) })}</p>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}
