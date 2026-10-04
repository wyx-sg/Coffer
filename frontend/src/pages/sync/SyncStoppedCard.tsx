// frontend/src/pages/sync/SyncStoppedCard.tsx
//
// What a stopped round is waiting on, on the Status tab between the area
// tiles and the Rounds table (spec vault-sync). A round stopped on conflicts
// lists the files both Macs changed (6.4.05); a round the deletion breaker
// held lists the folders it would delete from, with each folder's share
// (6.4.09). Every row opens the sub-view that answers it — Resolve conflicts
// at that file, or Review held deletions. The status banner above the tiles
// carries the explanation and the page's button; this card is the list.
//
// Gated on the status the page already polls, so the stop is fetched only
// while the status says a round is stopped.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { StoppedRound, SyncHold } from "@/lib/api/sync";
import { useSyncStatus } from "@/lib/hooks/useSync";
import { useSyncStop } from "@/lib/hooks/useSyncStop";
import { SyncDifferRows } from "./SyncDifferRows";
import { share } from "./syncConflictFormat";

const CARD = "overflow-hidden rounded-xl border border-border bg-surface-raised";
const ROW_LINK =
  "flex min-w-0 items-center gap-2.5 px-3.5 transition-colors duration-fast hover:bg-surface-hover";

function ConflictsCard({ round }: { round: StoppedRound }) {
  const { t } = useTranslation();
  return (
    <section
      className="flex flex-col gap-2.5"
      data-testid="sync-conflicts"
      aria-label={t("sync.conflicts.title")}
    >
      <h2 className="text-md font-semibold text-text">{t("sync.conflicts.title")}</h2>
      <SyncDifferRows
        files={round.files}
        href={(file) => `/sync/conflicts?path=${encodeURIComponent(file.path)}`}
        status={(file) =>
          file.answer
            ? { tone: "ok", label: t("sync.conflicts.resolved") }
            : { tone: "err", label: t("sync.conflicts.unresolved") }
        }
        testId={(file) => `conflict-${file.path}`}
      />
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
