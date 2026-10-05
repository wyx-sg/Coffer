// frontend/src/pages/sync/syncPendingFiles.ts
//
// What waits to push, one entry per file: the waiting commits come newest
// first and a file can be in several of them (four saves of one resource are
// one change to review). The entry carries the newest commit's writer and
// time, and the net mark — removed if the newest commit removed it, added if
// the oldest added it, otherwise modified.
import type { SyncChange, WaitingCommit } from "@/lib/api/sync";

export interface PendingFile {
  path: string;
  status: SyncChange["status"];
  writer: string;
  time: string;
}

export function pendingFiles(waiting: readonly WaitingCommit[]): PendingFile[] {
  const byPath = new Map<string, { newest: WaitingCommit; statuses: SyncChange["status"][] }>();
  for (const commit of waiting) {
    for (const change of commit.changes) {
      const seen = byPath.get(change.path);
      if (seen) seen.statuses.push(change.status);
      else byPath.set(change.path, { newest: commit, statuses: [change.status] });
    }
  }
  return [...byPath.entries()].map(([path, { newest, statuses }]) => ({
    path,
    status:
      statuses[0] === "removed"
        ? "removed"
        : statuses[statuses.length - 1] === "added"
          ? "added"
          : "modified",
    writer: newest.writer,
    time: newest.time,
  }));
}

/** The daemon's writers, in the four words a person reads them as. */
export const WRITER: Record<string, string> = {
  user: "you",
  daemon: "coffer",
  curation: "coffer",
  sync: "coffer",
  disk: "disk",
  agent: "agent",
};
