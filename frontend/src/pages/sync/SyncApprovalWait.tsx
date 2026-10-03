// frontend/src/pages/sync/SyncApprovalWait.tsx — the push token waits for a person's approval.
//
// Asking the remote needs the push token, and a token that was never approved
// for this remote is held by the secret boundary until a person approves it in
// the desktop app (ADR only-a-present-human-sees-a-secret-or-sends-it-somewhere-new).
// That is a state to act on, not a failure to read: say so, let the person
// Review it in the global approvals dialog, and check again (the preview also
// asks again when the window regains focus).
import { useTranslation } from "react-i18next";
import { KeyRound, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";

export function SyncApprovalWait({
  onReview,
  onRetry,
}: {
  onReview: () => void;
  onRetry: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-2 py-2" role="status" data-testid="sync-join-waiting">
      <p className="flex items-center gap-2 text-sm font-label text-text">
        <KeyRound className="size-4 text-warning" aria-hidden />
        {t("sync.join.waiting.title")}
      </p>
      <p className="text-xs text-text-muted">{t("sync.join.waiting.body")}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onReview}>
          {t("sync.problem.review")}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onRetry}>
          <RotateCw aria-hidden />
          {t("sync.join.waiting.checkAgain")}
        </Button>
      </div>
    </div>
  );
}
