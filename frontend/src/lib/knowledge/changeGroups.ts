// frontend/src/lib/knowledge/changeGroups.ts
//
// How a collection's Change log groups its rows (spec knowledge "Record a tidy
// as one change"): a run of edits made on disk — a person saving in their
// editor, an agent writing files outside a tidy — reads as one entry when each
// came within ten minutes of the one before, so a burst of saves is not a
// screen of rows. Every other change stays one row of its own; a tidy already
// is one change. Pure, so it is unit-tested without a component.
import type { ChangeOut } from "@/lib/api/knowledge";

/** Disk edits further apart than this start a new group. */
const DISK_GROUP_GAP_MS = 10 * 60 * 1000;

export type ChangeGroup =
  | { kind: "one"; change: ChangeOut }
  | { kind: "disk"; changes: ChangeOut[] };

function isDiskEdit(change: ChangeOut): boolean {
  return change.writer === "disk";
}

/** The feed (newest first) as Change log entries, newest first. */
export function groupChanges(changes: readonly ChangeOut[]): ChangeGroup[] {
  const groups: ChangeGroup[] = [];
  for (const change of changes) {
    const last = groups[groups.length - 1];
    if (isDiskEdit(change) && last?.kind === "disk") {
      const previous = last.changes[last.changes.length - 1];
      const gap = new Date(previous.time).getTime() - new Date(change.time).getTime();
      if (gap <= DISK_GROUP_GAP_MS) {
        last.changes.push(change);
        continue;
      }
    }
    groups.push(isDiskEdit(change) ? { kind: "disk", changes: [change] } : { kind: "one", change });
  }
  return groups;
}

/** The files a group of changes touched, each once, with the lines added
 *  and removed summed over the group. */
export function groupDocuments(
  changes: readonly ChangeOut[],
): { path: string; added: number; removed: number }[] {
  const byPath = new Map<string, { path: string; added: number; removed: number }>();
  for (const change of changes) {
    for (const doc of change.documents) {
      const seen = byPath.get(doc.path);
      if (seen) {
        seen.added += doc.added;
        seen.removed += doc.removed;
      } else {
        byPath.set(doc.path, { path: doc.path, added: doc.added, removed: doc.removed });
      }
    }
  }
  return [...byPath.values()];
}
