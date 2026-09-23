// frontend/src/pages/sync/syncRunSearch.ts
//
// What a free-text search over the Runs table matches against.
//
// Split out of `syncRunColumns.tsx`, which renders rows and was over its size
// cap. The rule worth keeping in one place is the second function's: a folded
// row answers for what it SHOWS, never for its members' fields, so searching
// for a commit cannot surface a fold that merely contains one — clicking it
// would not reveal it.
import type { TFunction } from "i18next";

import type { RunRecord } from "@/lib/api/sync";
import { formatDateTime } from "@/lib/utils";
import { statusLabel } from "./syncRunColumns";
import { groupSpan, type SyncRunRow } from "./syncRunRows";

/** What a free-text search matches against, for either kind of row.
 *
 * A folded row answers for the stretch it stands in for — its own span and its
 * one outcome — not its members' fields. Searching for a commit should not
 * surface a fold that merely contains one, because the fold does not show it
 * and clicking it would not reveal it. */
export function rowSearchHaystack(t: TFunction, row: SyncRunRow): string {
  if (row.kind === "group") {
    const span = groupSpan(row.runs);
    return [formatDateTime(span.from), formatDateTime(span.to), statusLabel(t, row.status)]
      .join(" ")
      .toLowerCase();
  }
  return runSearchHaystack(t, row.run);
}

/** What a free-text search on one round matches against. Not exported: every
 *  caller goes through `rowSearchHaystack`, which knows about folds too, and a
 *  second entry point is how a search that ignores them creeps back. */
function runSearchHaystack(t: TFunction, run: RunRecord): string {
  return [
    formatDateTime(run.finished_at),
    statusLabel(t, run.status),
    run.status,
    run.join ?? "",
    run.commit ?? "",
    ...run.conflicts,
    ...run.agent_resolved,
    ...run.locked_refs,
    ...run.failures.map((f) => `${f.path} ${f.reason}`),
    run.error ?? "",
  ]
    .join(" ")
    .toLowerCase();
}
