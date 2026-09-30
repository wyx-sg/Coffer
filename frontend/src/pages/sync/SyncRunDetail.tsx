// frontend/src/pages/sync/SyncRunDetail.tsx
//
// One round opened up, in the drawer beside the Rounds table (6.5.04): the
// four things every round does, in order — 1 the safety snapshot it took
// before checking anything out, 2 the commits it pulled and from whom, 3 what
// it applied here, 4 what it pushed — then git's own words when it could not
// finish. The footer rolls it back, or opens Activity, where the change the
// round wrote sits among everything else that happened.
//
// A folded row opens the same drawer onto the rounds it stands for, each of
// which opens in turn: folding hides rows, never the rounds in them (spec
// vault-sync "Fold consecutive quiet rounds into one row").
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Undo2 } from "lucide-react";

import { StatusPill } from "@/components/status/StatusPill";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { SyncRound } from "@/lib/api/sync";
import { canRollBack } from "./syncRowActions";
import { statusTone } from "./syncRoundStatus";
import { commitsCell, outcomeLabel } from "./syncRoundLabel";
import { groupSpan, type SyncRunRow } from "./syncRunRows";
import { RoundBody } from "./SyncRoundBody";
import { drawerTitle, seconds } from "./syncRoundDrawer";
import { daySpan, dayTime } from "./syncTime";

function GroupBody({ runs, onOpen }: { runs: SyncRound[]; onOpen: (run: SyncRound) => void }) {
  const { t } = useTranslation();
  const shared = runs[0]?.detail ?? null;
  return (
    <div className="space-y-3">
      {/* A stretch of failures shares one message — that is what let them fold. */}
      {shared ? (
        <pre className="whitespace-pre-wrap break-words rounded-lg bg-surface-sunken px-3 py-2.5 font-mono text-xs text-danger">
          {shared}
        </pre>
      ) : null}
      <ul className="divide-y divide-border-subtle rounded-lg border border-border">
        {runs.map((run) => (
          <li key={`${run.id}-${run.finished_at}`}>
            <button
              type="button"
              className="flex w-full items-center px-3 py-2 text-left text-xs text-text hover:bg-surface-hover"
              onClick={() => onOpen(run)}
            >
              {dayTime(run.finished_at, t)}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface Props {
  /** The row whose drawer is open, or null. */
  row: SyncRunRow | null;
  onClose: () => void;
  /** Open another row (a round inside a fold). */
  onOpen: (row: SyncRunRow) => void;
  onRollback: (run: SyncRound & { id: number }) => void;
}

export function SyncRunDetail({ row, onClose, onOpen, onRollback }: Props) {
  const { t } = useTranslation();
  const run = row?.kind === "run" ? row.run : null;
  const tone = run ? statusTone(run.status) : "muted";
  return (
    <Sheet open={row !== null} onOpenChange={(open) => (open ? null : onClose())}>
      <SheetContent className="max-w-[480px]" aria-describedby={undefined}>
        {row?.kind === "run" && run ? (
          <>
            <SheetHeader>
              <SheetTitle className="font-sans">{drawerTitle(t, run)}</SheetTitle>
              <SheetDescription className="flex flex-wrap items-center gap-2">
                <StatusPill tone={tone === "error" ? "err" : tone === "muted" ? "off" : tone}>
                  {tone === "ok" ? t("sync.drawer.finished") : outcomeLabel(t, run.status)}
                </StatusPill>
                <span className="font-mono">{commitsCell(run)}</span>
                <span>
                  · {t("sync.drawer.took", { seconds: seconds(run.started_at, run.finished_at) })}
                </span>
              </SheetDescription>
            </SheetHeader>
            <SheetBody>
              <RoundBody run={run} />
            </SheetBody>
            <SheetFooter>
              {canRollBack(run) ? (
                <Button type="button" variant="outline" onClick={() => onRollback(run)}>
                  <Undo2 aria-hidden />
                  {t("sync.drawer.rollBack")}
                </Button>
              ) : null}
              <Button asChild variant="ghost" className="ml-auto">
                <Link to="/activity?tab=changes">{t("sync.drawer.viewActivity")}</Link>
              </Button>
            </SheetFooter>
          </>
        ) : row?.kind === "group" ? (
          <>
            <SheetHeader>
              <SheetTitle className="font-sans">
                {t("sync.rounds.folded", {
                  label: outcomeLabel(t, row.status),
                  count: row.runs.length,
                })}
              </SheetTitle>
              <SheetDescription>
                {daySpan(groupSpan(row.runs).from, groupSpan(row.runs).to, t)}
              </SheetDescription>
            </SheetHeader>
            <SheetBody>
              <GroupBody
                runs={row.runs}
                onOpen={(r) =>
                  onOpen({
                    kind: "run",
                    id: r.id === null ? `at-${r.finished_at}` : String(r.id),
                    run: r,
                  })
                }
              />
            </SheetBody>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
