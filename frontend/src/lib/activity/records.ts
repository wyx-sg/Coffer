// src/lib/activity/records.ts — the three records Activity shows, as one row shape, and the filters over them.
//
// The Activity page reads three logs from their owners' routes (spec web-ui
// "Read each Activity tab from its record owner's route"): the audit log, the
// MCP invocation log and the daemon log. Each keeps its own wire shape; this
// module wraps each row in one `ActivityRecord` — a stable key, a time and the
// row itself — so the Everything tab can merge them into one newest-first
// stream and every tab can filter, hold and export with the same code. Pure
// functions only: no queries, no React.
import type { components } from "@/lib/api/types";

export type AuditEntry = components["schemas"]["AuditEntryOut"];
export type Invocation = components["schemas"]["InvocationOut"];
export type DaemonLogRecord = components["schemas"]["DaemonLogRecordOut"];

/** Which log a record came from. */
export type ActivitySource = "change" | "call" | "daemon";

/** The four tabs, in order; `everything` merges the other three. */
export const ACTIVITY_TABS = ["everything", "changes", "mcp", "daemon"] as const;
export type ActivityTab = (typeof ACTIVITY_TABS)[number];

/** The sources each tab reads. */
export const TAB_SOURCES: Record<ActivityTab, readonly ActivitySource[]> = {
  everything: ["change", "call", "daemon"],
  changes: ["change"],
  mcp: ["call"],
  daemon: ["daemon"],
};

/** @ui-only One row of any of the three logs. `at` is null only for a daemon line nothing dates. */
export type ActivityRecord =
  | { source: "change"; key: string; at: string; entry: AuditEntry }
  | { source: "call"; key: string; at: string; call: Invocation }
  | { source: "daemon"; key: string; at: string | null; log: DaemonLogRecord };

export function fromAudit(entry: AuditEntry): ActivityRecord {
  return { source: "change", key: `change:${entry.id}`, at: entry.timestamp, entry };
}

export function fromCall(call: Invocation): ActivityRecord {
  return { source: "call", key: `call:${call.id}`, at: call.timestamp, call };
}

/**
 * Where an undated daemon line gets its time from. The route returns the tail
 * newest-first, and a line that was not JSON is written right after the record
 * that raised it, so it borrows from the nearest record after it — failing
 * that, before it. A line with nothing to borrow from keeps null.
 */
function borrowedTimestamp(records: readonly DaemonLogRecord[], index: number): string | null {
  for (let i = index + 1; i < records.length; i += 1) {
    const at = records[i].timestamp;
    if (at) return at;
  }
  for (let i = index - 1; i >= 0; i -= 1) {
    const at = records[i].timestamp;
    if (at) return at;
  }
  return null;
}

/**
 * One page of the daemon log as records. The route names where each line
 * starts in the file (`offset`), which is its identity: the file only grows at
 * its end, so the same line has the same key on every read, whichever page it
 * arrives on. A line with no time of its own (a traceback's header) borrows
 * from the nearest record in the page, as above.
 */
export function fromDaemonTail(records: readonly DaemonLogRecord[]): ActivityRecord[] {
  return records.map((log, i) => ({
    source: "daemon",
    key: `daemon:${log.offset}`,
    at: log.timestamp || borrowedTimestamp(records, i),
    log,
  }));
}

function timeMs(at: string | null): number {
  if (!at) return 0;
  const ms = Date.parse(at);
  return Number.isNaN(ms) ? 0 : ms;
}

/** Newest first; a record with no time sinks to the end of its run. */
function compareNewestFirst(a: ActivityRecord, b: ActivityRecord): number {
  return timeMs(b.at) - timeMs(a.at);
}

/** Merge several newest-first lists into one, without duplicates. */
export function mergeNewestFirst(lists: readonly (readonly ActivityRecord[])[]): ActivityRecord[] {
  const byKey = new Map<string, ActivityRecord>();
  for (const list of lists) for (const r of list) if (!byKey.has(r.key)) byKey.set(r.key, r);
  return [...byKey.values()].sort(compareNewestFirst);
}

export { timeMs as recordTimeMs };

// ---------------------------------------------------------------------------
// What a row says about itself
// ---------------------------------------------------------------------------

/** The label a call's server goes by: its current name, else the uid's own text. */
export function callServerLabel(call: Invocation): string {
  return call.resource_name ?? call.resource_uid;
}

/** The daemon logger a record names, if any. */
export function recordLogger(r: ActivityRecord): string {
  if (r.source !== "daemon") return "";
  const logger = r.log.record?.logger;
  return typeof logger === "string" ? logger : "";
}

/** A daemon record's level, lowercased ("" when the line stated none). */
export function daemonLevel(log: DaemonLogRecord): string {
  return (log.level ?? "").toLowerCase();
}

/** How serious a record is, for its icon tile and the error / warning tally. */
export function recordSeverity(r: ActivityRecord): "error" | "warning" | "none" {
  if (r.source === "call") {
    if (r.call.status === "error") return "error";
    if (r.call.status === "timeout" || r.call.status === "denied") return "warning";
    return "none";
  }
  if (r.source === "daemon") {
    const level = daemonLevel(r.log);
    if (level === "error" || level === "critical" || level === "exception") return "error";
    if (level === "warning" || level === "warn") return "warning";
  }
  return "none";
}

/** A duration in the unit a person reads it in: 12 ms, 1.3 s, 30.0 s. */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}
