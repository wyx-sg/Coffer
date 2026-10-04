// frontend/src/pages/sync/SyncConflictFooter.tsx
//
// The foot of Resolve conflicts: how many files have an answer, Leave for
// later (back to Sync, the round stays stopped and this Mac keeps working),
// and Continue round — offered once every file has one. Continuing writes the
// answers into the vault, checks the result out and pushes it. For a first
// join the primary is Apply choices, offered once any file has a version; the
// files left alone stay as they are.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import type { ResolveSource } from "./useResolveSource";

export function SyncConflictFooter({
  source,
  onDone,
}: {
  source: ResolveSource;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const join = source.mode === "join";
  const { ready, pending } = source.finish;
  const total = source.files.length;
  const resolved = source.chosen;

  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-border bg-surface-footer px-5 py-3">
      <p className="text-xs text-text-muted" data-testid="sync-conflicts-progress">
        {t(join ? "sync.resolve.progressJoin" : "sync.resolve.progress", { resolved, total })}
        {ready ? null : ` · ${t(join ? "sync.resolve.applyHint" : "sync.resolve.continueHint")}`}
      </p>
      <div className="ml-auto flex items-center gap-2">
        <Button asChild variant="ghost">
          <Link to="/sync">{t("sync.resolve.later")}</Link>
        </Button>
        <Button
          type="button"
          disabled={!ready}
          loading={pending}
          onClick={() => source.finish.run(onDone)}
        >
          {join
            ? t("sync.resolve.apply")
            : pending
              ? t("sync.resolve.continuing")
              : t("sync.resolve.continue")}
        </Button>
      </div>
    </div>
  );
}
