// frontend/src/pages/sync/SyncStoppedCard.tsx
//
// What a stopped round is waiting on, on the Status tab between the area
// tiles and the Rounds table (spec vault-sync). A round stopped on conflicts
// lists the files both Macs changed (6.5.05); a round the deletion breaker
// held lists the folders it would delete from, with each folder's share
// (6.5.08). Every row opens the sub-view that answers it — Resolve conflicts
// at that file, or Review held deletions. The status banner above the tiles
// carries the explanation and the page's button; this card is the list.
//
// Gated on the status the page already polls, so the stop is fetched only
// while the status says a round is stopped.
import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { StatusPill } from "@/components/status/StatusPill";
import type { StoppedRound, SyncHold } from "@/lib/api/sync";
import { useSyncStatus } from "@/lib/hooks/useSync";
import { useSyncStop } from "@/lib/hooks/useSyncStop";
import { areaLabel, clock, otherMachine, share } from "./syncConflictFormat";

const CARD = "overflow-hidden rounded-xl border border-border bg-surface-raised";
const ROW_LINK =
  "flex min-w-0 items-center gap-2.5 px-3.5 transition-colors duration-fast hover:bg-surface-hover";

function ConflictsCard({ round }: { round: StoppedRound }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  return (
    <section className={CARD} data-testid="sync-conflicts" aria-labelledby="sync-conflicts-title">
      <h3
        id="sync-conflicts-title"
        className="flex min-h-9 items-center px-3.5 text-xs font-semibold text-text-muted"
      >
        {t("sync.conflicts.title")}
      </h3>
      <ul>
        {round.files.map((file) => (
          <li key={file.path} className="border-t border-border-subtle">
            <Link
              to={`/sync/conflicts?path=${encodeURIComponent(file.path)}`}
              className={`${ROW_LINK} min-h-11 py-1.5`}
              data-testid={`conflict-${file.path}`}
            >
              <FileText className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="truncate font-mono text-xs text-text">{file.path}</span>
                <span className="text-xs text-text-muted">
                  {t("sync.conflicts.row", {
                    area: areaLabel(t, file.area),
                    mine: clock(file.ours_time, locale),
                    machine: otherMachine(t, file),
                    theirs: clock(file.theirs_time, locale),
                  })}
                </span>
              </span>
              <StatusPill
                tone={file.answer ? "ok" : "err"}
                className="ml-auto h-5 rounded-sm px-[7px] text-2xs font-label"
              >
                {file.answer ? t("sync.conflicts.resolved") : t("sync.conflicts.unresolved")}
              </StatusPill>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function HoldCard({ hold }: { hold: SyncHold }) {
  const { t } = useTranslation();
  return (
    <section className={CARD} data-testid="sync-hold" aria-label={t("sync.hold.label")}>
      <ul className="flex flex-col py-1.5">
        {hold.groups.map((group) => {
          const count = group.paths.length;
          const whole = count >= group.total;
          return (
            <li key={group.folder}>
              <Link to="/sync/deletions" className={`${ROW_LINK} min-h-8 gap-2`}>
                <span
                  aria-hidden
                  className="inline-flex w-4 shrink-0 justify-center font-mono text-xs font-medium text-danger"
                >
                  −
                </span>
                <span className="min-w-0 truncate font-mono text-xs text-text">
                  {group.folder.endsWith("/") ? group.folder : `${group.folder}/`}
                </span>
                <span className="ml-auto whitespace-nowrap text-xs text-text-subtle">
                  {whole
                    ? t("sync.hold.files", { count })
                    : t("sync.hold.share", { count, percent: share(count, group.total) })}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function SyncStoppedCard() {
  const { data: status } = useSyncStatus();
  const stopped = !!status && (status.conflicts > 0 || status.held > 0);
  const { data } = useSyncStop(stopped);
  const round = stopped && data?.stopped ? data.round : null;
  if (!round) return null;
  if (round.kind === "hold") return round.hold ? <HoldCard hold={round.hold} /> : null;
  return <ConflictsCard round={round} />;
}
