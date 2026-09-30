// frontend/src/pages/sync/SyncDeletionGroups.tsx
//
// The held files by folder (6.5.09). Each folder's header names its area and
// its share — "12 of 20 files" means one thing, "12 of 12" another — and the
// first few paths are listed, the rest counted.
import { useTranslation } from "react-i18next";

import type { SyncHold } from "@/lib/api/sync";
import { folderLabel } from "./syncConflictFormat";

/** Past this, a folder's paths are counted rather than listed. */
const MAX_PATHS = 6;

export function SyncDeletionGroups({ hold, who }: { hold: SyncHold; who: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4">
      {hold.groups.map((group) => {
        const count = group.paths.length;
        const shown = group.paths.slice(0, MAX_PATHS);
        return (
          <section key={group.folder} className="flex flex-col gap-2" data-testid="sync-held-group">
            <h3 className="text-2xs font-semibold uppercase tracking-[.02em] text-text-muted">
              {folderLabel(t, group.folder)} ·{" "}
              {count >= group.total
                ? t("sync.deletions.groupAll", { count })
                : t("sync.deletions.groupSome", { count, total: group.total })}
            </h3>
            <ul className="flex flex-col rounded-lg bg-surface-sunken px-3 py-1.5">
              {shown.map((path) => (
                <li key={path} className="flex min-h-7 min-w-0 items-center gap-2">
                  <span
                    aria-hidden
                    className="w-4 shrink-0 text-center font-mono text-xs text-danger"
                  >
                    −
                  </span>
                  <span className="min-w-0 truncate font-mono text-xs text-text">{path}</span>
                  <span className="ml-auto whitespace-nowrap text-xs text-text-subtle">{who}</span>
                </li>
              ))}
              {count > shown.length ? (
                <li className="flex min-h-7 items-center pl-6 text-xs text-text-subtle">
                  {t("sync.deletions.more", { count: count - shown.length })}
                </li>
              ) : null}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
