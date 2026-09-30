// frontend/src/pages/sync/SyncConflictFooter.tsx
//
// The foot of Resolve conflicts: how many files have an answer, Leave for
// later (back to Sync, the round stays stopped and this Mac keeps working),
// and Continue round — offered once every file has one. Continuing writes the
// answers into the vault, checks the result out and pushes it.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import type { StoppedRound } from "@/lib/api/sync";
import { useContinueRound } from "@/lib/hooks/useSyncStop";

export function SyncConflictFooter({ round, onDone }: { round: StoppedRound; onDone: () => void }) {
  const { t } = useTranslation();
  const proceed = useContinueRound();
  const total = round.files.length;
  const resolved = total - round.unanswered;
  const ready = round.unanswered === 0;

  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-border bg-surface-footer px-5 py-3">
      <p className="text-xs text-text-muted" data-testid="sync-conflicts-progress">
        {t("sync.resolve.progress", { resolved, total })}
        {ready ? null : ` · ${t("sync.resolve.continueHint")}`}
      </p>
      <div className="ml-auto flex items-center gap-2">
        <Button asChild variant="ghost">
          <Link to="/sync">{t("sync.resolve.later")}</Link>
        </Button>
        <Button
          type="button"
          disabled={!ready}
          loading={proceed.isPending}
          onClick={() => proceed.mutate(undefined, { onSuccess: onDone })}
        >
          {proceed.isPending ? t("sync.resolve.continuing") : t("sync.resolve.continue")}
        </Button>
      </div>
    </div>
  );
}
