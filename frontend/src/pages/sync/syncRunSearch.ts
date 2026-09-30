// frontend/src/pages/sync/syncRunSearch.ts
//
// What a free-text search over the Runs table matches against. A folded row
// answers for what it SHOWS, never for its members' fields, so searching for a
// commit cannot surface a fold that merely contains one — clicking it would
// not reveal it.
import type { TFunction } from "i18next";

import type { SyncRound } from "@/lib/api/sync";
import { formatDateTime } from "@/lib/utils";
import { statusLabel } from "./syncRoundStatus";
import { groupSpan, type SyncRunRow } from "./syncRunRows";

export function rowSearchHaystack(t: TFunction, row: SyncRunRow): string {
  if (row.kind === "group") {
    const span = groupSpan(row.runs);
    return [formatDateTime(span.from), formatDateTime(span.to), statusLabel(t, row.status)]
      .join(" ")
      .toLowerCase();
  }
  return runSearchHaystack(t, row.run);
}

function runSearchHaystack(t: TFunction, run: SyncRound): string {
  return [
    formatDateTime(run.finished_at),
    statusLabel(t, run.status),
    run.status,
    run.from_commit ?? "",
    run.to_commit ?? "",
    run.snapshot ?? "",
    ...run.with_machines,
    ...run.pulled.map((c) => `${c.version} ${c.machine ?? ""}`),
    ...run.applied.map((c) => c.path),
    ...run.pushed.map((c) => c.path),
    run.detail ?? "",
  ]
    .join(" ")
    .toLowerCase();
}
