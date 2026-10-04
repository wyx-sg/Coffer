// frontend/src/pages/sync/SyncWaitingList.tsx
//
// What this Mac has that the remote does not have yet (6.4.02): every file
// the next round pushes, one line each in a bordered list — its change mark
// and path, then who wrote it and when. The writer matters: a file a person
// edited, one an agent wrote and one Coffer's own upkeep rewrote are different
// things to find in the list when something looks wrong. Past five lines the
// list says "Showing 5 of 37 · Show all" (principle 21).
import { useTranslation } from "react-i18next";

import { ShowAllRow } from "@/components/LongList";
import { useLongList } from "@/components/useLongList";
import type { WaitingCommit } from "@/lib/api/sync";
import { ChangeMark, FILE_LIST, FILE_ROW } from "./SyncChangeMark";
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
  const { visible, shown, total, collapsed, expand, listClassName } = useLongList(rows);
  if (rows.length === 0) return null;

  return (
    <div className={FILE_LIST} data-testid="sync-waiting" aria-label={t("sync.waiting.label")}>
      <ul className={listClassName}>
        {visible.map(({ commit, change, key }) => (
          <li key={key} className={FILE_ROW}>
            <ChangeMark status={change.status} />
            <span className="min-w-0 flex-1 truncate font-mono text-xs text-text">
              {change.path}
            </span>
            <span className="shrink-0 text-xs text-text-subtle">
              {t(`sync.waiting.writer.${WRITER[commit.writer] ?? "coffer"}`)} · {clock(commit.time)}
            </span>
          </li>
        ))}
      </ul>
      {collapsed ? <ShowAllRow shown={shown} total={total} onShowAll={expand} /> : null}
    </div>
  );
}
