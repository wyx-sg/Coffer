// frontend/src/pages/sync/SyncWaitingList.tsx
//
// What this Mac has that the remote does not have yet (6.5.02): every file
// the next round pushes, one line each — its change mark and path, then who
// wrote it and when. The writer matters: a file a person edited, one an agent
// wrote and one Coffer's own upkeep rewrote are different things to find in
// the list when something looks wrong.
import { useTranslation } from "react-i18next";

import type { WaitingCommit } from "@/lib/api/sync";
import { changeLine } from "./syncRoundStatus";
import { clock } from "./syncTime";

/** The daemon's writers, in the four words a person reads them as. */
const WRITER: Record<string, string> = {
  user: "you",
  daemon: "coffer",
  curation: "coffer",
  sync: "coffer",
  disk: "disk",
  agent: "agent",
};

export function SyncWaitingList({ waiting }: { waiting: WaitingCommit[] }) {
  const { t } = useTranslation();
  const rows = waiting.flatMap((commit) =>
    commit.changes.map((change) => ({ commit, change, key: `${commit.version}:${change.path}` })),
  );
  if (rows.length === 0) return null;

  return (
    <ul
      className="space-y-1 rounded-xl bg-surface-sunken px-3.5 py-2.5"
      data-testid="sync-waiting"
      aria-label={t("sync.waiting.label")}
    >
      {rows.map(({ commit, change, key }) => (
        <li key={key} className="flex items-center gap-3 text-xs">
          <span className="min-w-0 flex-1 truncate font-mono text-text">{changeLine(change)}</span>
          <span className="shrink-0 text-text-muted">
            {t(`sync.waiting.writer.${WRITER[commit.writer] ?? "coffer"}`)} · {clock(commit.time)}
          </span>
        </li>
      ))}
    </ul>
  );
}
