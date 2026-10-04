// frontend/src/pages/sync/syncConflictFormat.ts
//
// The words the conflict and deletion views share: when a side changed a file
// ("14:10" today, "12 Aug 14:10" before), which area a path is in, what one
// file's answer reads as in the file list, and the unified diff the daemon
// sends (`take_theirs`) split into rows with line numbers. Pure: the
// translator and the locale are passed in.
import type { TFunction } from "i18next";

import type { DiffLine } from "@/lib/changePreview/changeCounts";
import { ApiError, translateApiError } from "@/lib/api/errors";
import type { ConflictFile } from "@/lib/api/sync";

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function parts(iso: string, locale: string, now: Date) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const time = new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
  const date = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(d);
  return { time, date, today: sameDay(d, now) };
}

/** "14:10" today, "12 Aug 14:10" on another day, "—" when unknown. */
export function clock(iso: string | null, locale: string, now = new Date()): string {
  if (!iso) return "—";
  const p = parts(iso, locale, now);
  if (!p) return iso;
  return p.today ? p.time : `${p.date} ${p.time}`;
}

/** "today at 11:02" / "12 Aug at 11:02", or null when the time is unknown. */
export function when(
  t: TFunction,
  iso: string | null,
  locale: string,
  now = new Date(),
): string | null {
  if (!iso) return null;
  const p = parts(iso, locale, now);
  if (!p) return null;
  return p.today
    ? t("sync.resolve.today", { time: p.time })
    : t("sync.resolve.onDay", { date: p.date, time: p.time });
}

const AREA_KEY: Record<string, string> = {
  knowledge: "knowledge",
  skills: "skills",
  resources: "resources",
  secret: "secret",
  machines: "machines",
};

/** An area's name as the Status tiles say it; an unknown area as it came. */
export function areaLabel(t: TFunction, area: string): string {
  const key = AREA_KEY[area];
  return key ? t(`sync.conflicts.area.${key}`) : area;
}

/** The other side's machine, by name when the round knows it. */
export function otherMachine(t: TFunction, file: ConflictFile): string {
  return file.theirs_machine ?? t("sync.conflicts.otherMachine");
}

/** What a file's answer reads as under its path in the file list. */
export function fileState(t: TFunction, file: ConflictFile, editing: boolean): string {
  if (file.answer === "mine") return t("sync.resolve.state.mine");
  if (file.answer === "theirs") {
    return t("sync.resolve.state.theirs", { machine: otherMachine(t, file) });
  }
  if (file.answer === "edited") {
    return file.agent_state === "merged_by_agent"
      ? t("sync.resolve.state.agentResolved")
      : t("sync.resolve.state.edited");
  }
  if (editing) return t("sync.resolve.state.editing");
  if (file.agent_state === "merged_by_agent") return t("sync.resolve.state.merged");
  if (file.agent_state === "handed_off") return t("sync.resolve.state.handedOff");
  return file.secret ? t("sync.resolve.state.secret") : t("sync.resolve.state.open");
}

/** Whether "Hand off to <Agent>" is offered for a file: only a merge, and only while it has no answer. */
export function canAskAgent(file: ConflictFile): boolean {
  return file.agent_mergeable && !file.secret && file.answer === null;
}

const HUNK = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$/;

export interface ParsedDiff {
  lines: DiffLine[];
  added: number;
  removed: number;
}

/** A unified diff as rows: hunk headers, then each line with its old and new
 *  numbers. The `---`/`+++` file header and "\ No newline" notes are dropped. */
export function parseUnifiedDiff(text: string): ParsedDiff {
  const lines: DiffLine[] = [];
  let added = 0;
  let removed = 0;
  let oldNo = 0;
  let newNo = 0;
  let inHunk = false;
  for (const raw of text.split("\n")) {
    const line = raw.replace(/\r$/, "");
    const hunk = HUNK.exec(line);
    if (hunk) {
      oldNo = Number(hunk[1]);
      newNo = Number(hunk[2]);
      inHunk = true;
      lines.push({ kind: "hunk", text: line.replace(/^@@ -/, "@@ −") });
      continue;
    }
    if (!inHunk || line.startsWith("\\")) continue;
    if (line.startsWith("+")) {
      lines.push({ kind: "add", text: line.slice(1), newNo: newNo++ });
      added += 1;
    } else if (line.startsWith("-")) {
      lines.push({ kind: "remove", text: line.slice(1), oldNo: oldNo++ });
      removed += 1;
    } else if (line.startsWith(" ")) {
      lines.push({ kind: "context", text: line.slice(1), oldNo: oldNo++, newNo: newNo++ });
    }
  }
  return { lines, added, removed };
}

/** A held folder as its header says it: "Knowledge · archive/chat-bot". */
export function folderLabel(t: TFunction, folder: string): string {
  const [area, ...rest] = folder.replace(/\/$/, "").split("/");
  const name = areaLabel(t, area ?? folder);
  return rest.length > 0 ? `${name} · ${rest.join("/")}` : name;
}

/** A folder's share of its files, as a whole percent. */
export function share(count: number, total: number): number {
  return total > 0 ? Math.round((count / total) * 100) : 100;
}

/** A refused answer, in place. A copy that still has conflict markers is
 *  refused with the line it stopped at, which only the daemon's own message
 *  carries — so that one is shown verbatim, every other in the app's words. */
export function refusal(t: TFunction, error: unknown): string {
  if (error instanceof ApiError && error.code === "SYNC_CONFLICT_MARKERS_LEFT") {
    return error.envelopeMessage;
  }
  return translateApiError(t, error);
}
