// frontend/src/pages/sync/SyncConflictCard.tsx
//
// A round that stopped on files both machines changed (spec vault-sync). The
// round checked nothing out and pushed nothing: it is waiting for a person to
// say, file by file, which version to keep — this Mac's, the other machine's,
// or one they edited by hand — and then to continue it.
//
// Leaving it for later is a real answer: the vault stays exactly as it is
// here, and the next round stops at the same place until someone comes back.
import { useTranslation } from "react-i18next";
import { GitMerge } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { StoppedRound } from "@/lib/api/sync";
import { useContinueRound } from "@/lib/hooks/useSyncStop";
import { SyncConflictFileRow } from "./SyncConflictFileRow";

const COLUMNS = ["file", "area", "mine", "theirs", "answer", "actions"] as const;

export function SyncConflictCard({ round }: { round: StoppedRound }) {
  const { t } = useTranslation();
  const proceed = useContinueRound();
  const total = round.files.length;
  const resolved = total - round.unanswered;

  return (
    <Card data-testid="sync-conflicts">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <GitMerge className="size-4" aria-hidden />
          {t("sync.conflicts.title", { count: total })}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t("sync.conflicts.body")}</p>
        <Table>
          <TableHeader>
            <TableRow>
              {COLUMNS.map((c) => (
                <TableHead key={c} className={c === "actions" ? "text-right" : ""}>
                  {t(`sync.conflicts.columns.${c}`)}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {round.files.map((file) => (
              <SyncConflictFileRow key={file.path} file={file} />
            ))}
          </TableBody>
        </Table>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm" data-testid="sync-conflicts-progress">
            {t("sync.conflicts.progress", { resolved, total })}
          </p>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground">{t("sync.conflicts.later")}</span>
            <Button
              type="button"
              disabled={round.unanswered > 0 || proceed.isPending}
              onClick={() => proceed.mutate()}
            >
              {proceed.isPending ? t("sync.conflicts.continuing") : t("sync.conflicts.continue")}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
