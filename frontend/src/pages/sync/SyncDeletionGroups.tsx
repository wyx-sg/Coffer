// frontend/src/pages/sync/SyncDeletionGroups.tsx
//
// The held files by folder (6.4.10): a 13/600 heading naming the area, then a
// bordered list, one file per line with who deleted it. Past four files a
// folder says "Showing 4 of 12 · Show all" and expands in place.
import { useTranslation } from "react-i18next";

import { ShowAllRow } from "@/components/LongList";
import { useLongList } from "@/components/useLongList";
import type { SyncHold } from "@/lib/api/sync";
import { ChangeMark, FILE_LIST, FILE_ROW } from "./SyncChangeMark";
import { folderLabel } from "./syncConflictFormat";

/** The boards show four files before Show all. */
const LIMIT = 4;

function Group({ folder, paths, who }: { folder: string; paths: string[]; who: string }) {
  const { t } = useTranslation();
  const { visible, shown, total, collapsed, expand, listClassName } = useLongList(paths, {
    limit: LIMIT,
  });
  return (
    <section className="flex flex-col gap-2" data-testid="sync-held-group">
      <h3 className="text-sm font-semibold text-text">{folderLabel(t, folder)}</h3>
      <div className={FILE_LIST}>
        <ul className={listClassName}>
          {visible.map((path) => (
            <li key={path} className={FILE_ROW}>
              <ChangeMark status="removed" />
              <span className="min-w-0 flex-1 truncate font-mono text-xs text-text">{path}</span>
              <span className="whitespace-nowrap text-xs text-text-subtle">{who}</span>
            </li>
          ))}
        </ul>
        {collapsed ? <ShowAllRow shown={shown} total={total} onShowAll={expand} /> : null}
      </div>
    </section>
  );
}

export function SyncDeletionGroups({ hold, who }: { hold: SyncHold; who: string }) {
  return (
    <>
      {hold.groups.map((group) => (
        <Group key={group.folder} folder={group.folder} paths={group.paths} who={who} />
      ))}
    </>
  );
}
