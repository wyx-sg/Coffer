// frontend/src/pages/sync/SyncRunDetail.tsx
//
// One round opened up, in the shared drawer beside the Rounds table (6.4.04,
// Foundations 0.4.02): the four things every round does, in order — 1 the
// safety snapshot it took before checking anything out, 2 the commits it
// pulled and from whom, 3 what it applied here, 4 what it pushed — then git's
// own words when it could not finish. The footer opens Activity, where the
// change the round wrote sits among everything else that happened, or rolls
// the round back (the only Roll back on the page).
//
// A folded row opens the same drawer onto the rounds it stands for, each of
// which opens in turn: folding hides rows, never the rounds in them (spec
// vault-sync "Fold consecutive quiet rounds into one row"). Previous and next
// step through the table's rows.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Drawer } from "@/components/Drawer";
import { Button } from "@/components/ui/button";
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
      <ul className="divide-y divide-border-subtle rounded-xl border border-border">
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
  /** Every row of the table, for previous / next. */
  rows: SyncRunRow[];
  onClose: () => void;
  /** Open another row (a round inside a fold, or the previous / next row). */
  onOpen: (row: SyncRunRow) => void;
  onRollback: (run: SyncRound & { id: number }) => void;
}

export function SyncRunDetail({ row, rows, onClose, onOpen, onRollback }: Props) {
  const { t } = useTranslation();
  const run = row?.kind === "run" ? row.run : null;
  const at = row ? rows.findIndex((r) => r.id === row.id) : -1;
  // A round opened from inside a fold is not a table row: no stepping from it.
  const stepping = at >= 0;

  let title = "";
  let subtitle: string | undefined;
  let footer = null;
  if (row?.kind === "run" && run) {
    const word =
      statusTone(run.status) === "ok" ? t("sync.drawer.finished") : outcomeLabel(t, run.status);
    title = drawerTitle(t, run);
    subtitle = [
      word,
      commitsCell(run),
      t("sync.drawer.took", { seconds: seconds(run.started_at, run.finished_at) }),
    ]
      .filter(Boolean)
      .join(" · ");
    footer = (
      <>
        <Button asChild variant="ghost">
          <Link to="/activity?tab=changes">{t("sync.drawer.viewActivity")}</Link>
        </Button>
        {canRollBack(run) ? (
          <Button type="button" variant="secondary" onClick={() => onRollback(run)}>
            {t("sync.drawer.rollBack")}
          </Button>
        ) : null}
      </>
    );
  } else if (row?.kind === "group") {
    const span = groupSpan(row.runs);
    title = t("sync.rounds.folded", { label: outcomeLabel(t, row.status), count: row.runs.length });
    subtitle = daySpan(span.from, span.to, t);
  }

  return (
    <Drawer
      open={row !== null}
      onOpenChange={(open) => (open ? null : onClose())}
      title={title}
      subtitle={subtitle}
      {...(stepping
        ? {
            onPrevious: () => onOpen(rows[at - 1]),
            onNext: () => onOpen(rows[at + 1]),
            hasPrevious: at > 0,
            hasNext: at < rows.length - 1,
          }
        : {})}
      footer={footer}
    >
      {row?.kind === "run" && run ? (
        <RoundBody run={run} />
      ) : row?.kind === "group" ? (
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
      ) : null}
    </Drawer>
  );
}
