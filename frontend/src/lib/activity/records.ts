// src/lib/activity/records.ts — the three records Activity shows, as one row shape, and the filters over them.
//
// The Activity page reads three logs from their owners' routes (spec web-ui
// "Read each Activity tab from its record owner's route"): the audit log, the
// MCP invocation log and the daemon log. Each keeps its own wire shape; this
// module wraps each row in one `ActivityRecord` — a stable key, a time and the
// row itself — so the Everything tab can merge them into one newest-first
// stream and every tab can filter, hold and export with the same code. Pure
// functions only: no queries, no React.
import type { TFunction } from "i18next";

import type { components } from "@/lib/api/types";
import { auditSearchHaystack, daemonSearchHaystack } from "./activityText";

export type AuditEntry = components["schemas"]["AuditEntryOut"];
export type Invocation = components["schemas"]["InvocationOut"];
export type DaemonLogRecord = components["schemas"]["DaemonLogRecordOut"];

/** The resource kinds a change can be about, in the order the kind filter lists them. */
export const CHANGE_KINDS = [
  "mcp_server",
  "skill",
  "agent",
  "provider",
  "channel",
  "knowledge",
  "memory",
] as const;

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
 * The daemon log tail as records. The route gives a line no id, so its key is
 * its time and message plus how many identical lines precede it in the same
 * tail — stable across two reads of the same file, so a poll recognises what
 * it has already shown.
 */
export function fromDaemonTail(records: readonly DaemonLogRecord[]): ActivityRecord[] {
  const seen = new Map<string, number>();
  const out: ActivityRecord[] = [];
  // Count occurrences oldest-first, so a new line at the head does not shift
  // the keys of the lines below it.
  for (let i = records.length - 1; i >= 0; i -= 1) {
    const log = records[i];
    const at = log.timestamp || borrowedTimestamp(records, i);
    const base = `${at ?? ""}|${log.event ?? ""}|${String(log.record?.raw ?? "")}`;
    const n = seen.get(base) ?? 0;
    seen.set(base, n + 1);
    out.push({ source: "daemon", key: `daemon:${base}|${n}`, at, log });
  }
  return out.reverse();
}

function timeMs(at: string | null): number {
  if (!at) return 0;
  const ms = Date.parse(at);
  return Number.isNaN(ms) ? 0 : ms;
}

/** Newest first; a record with no time sinks to the end of its run. */
export function compareNewestFirst(a: ActivityRecord, b: ActivityRecord): number {
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
// Filters
// ---------------------------------------------------------------------------

/** @ui-only Every Activity filter; each tab reads the ones its records afford. */
export interface ActivityFilters {
  /** A TIME_PRESETS key, or "custom" with from/to. */
  timeRange: string;
  from: string;
  to: string;
  /** Free text over what each row shows. */
  search: string;
  /** Who: "any", `agent:<uid>`, or `actor:<audit actor>`. */
  by: string;
  /** An MCP server's uid, or "any". */
  server: string;
  /** What: "any", "calls", "changes", "daemon", "not-daemon" or `change:<resource kind>`. */
  kind: string;
  /** An MCP call's status, or "any" (MCP calls tab). */
  status: string;
  /** Daemon log severity floor; "" is every level (Daemon log tab). */
  level: string;
  /** A daemon logger name, or "any" (Daemon log tab). */
  logger: string;
}

export const DEFAULT_FILTERS: ActivityFilters = {
  timeRange: "1h",
  from: "",
  to: "",
  search: "",
  by: "any",
  server: "any",
  kind: "any",
  status: "any",
  level: "",
  logger: "any",
};

/** Whether anything narrows the view beyond the default time window. */
export function filtersNarrow(f: ActivityFilters, tab: ActivityTab): boolean {
  if (f.search.trim() || f.by !== "any" || f.server !== "any") return true;
  if ((tab === "everything" || tab === "changes") && f.kind !== "any") return true;
  if (tab === "mcp" && f.status !== "any") return true;
  if (tab === "daemon" && (f.level !== "" || f.logger !== "any")) return true;
  return false;
}

/**
 * The sources a tab reads once its filters are applied: a kind, a server or a
 * who that only one or two logs can carry drops the others, so they are
 * neither fetched nor counted.
 */
export function sourcesFor(tab: ActivityTab, f: ActivityFilters): ActivitySource[] {
  let sources = [...TAB_SOURCES[tab]];
  if (tab === "everything") {
    if (f.kind === "calls") sources = ["call"];
    else if (f.kind === "daemon") sources = ["daemon"];
    else if (f.kind === "changes" || f.kind.startsWith("change:")) sources = ["change"];
    else if (f.kind === "not-daemon") sources = ["change", "call"];
  }
  if (f.server !== "any") sources = sources.filter((s) => s !== "daemon");
  if (f.by.startsWith("agent:")) sources = sources.filter((s) => s !== "daemon");
  else if (f.by.startsWith("actor:")) {
    const actor = f.by.slice("actor:".length);
    sources = sources.filter((s) => s === "change" || (s === "daemon" && actor === "system"));
  }
  return sources;
}

/** @ui-only What a predicate needs to know beyond the record. */
export interface FilterContext {
  t: TFunction;
  /** The custom range's upper bound, ISO; rolling presets have none. */
  until?: string;
  /** Agent uid → display name, for search and the who filter on changes. */
  agentNames: ReadonlyMap<string, string>;
  /** MCP server uid → name, for the server filter on changes. */
  serverNames: ReadonlyMap<string, string>;
}

/** The label a call's server goes by: its current name, else the uid's own text. */
export function callServerLabel(call: Invocation): string {
  return call.resource_name ?? call.resource_uid;
}

function callHaystack(call: Invocation, ctx: FilterContext): string {
  return [
    callServerLabel(call),
    call.capability_key,
    `${callServerLabel(call)}.${call.capability_key}`,
    call.status,
    call.error_message ?? "",
    call.session_id ?? "",
    call.agent_uid ? (ctx.agentNames.get(call.agent_uid) ?? "") : "",
  ]
    .join(" ")
    .toLowerCase();
}

/** The lowercased text a free-text search matches for one record. */
export function recordHaystack(r: ActivityRecord, ctx: FilterContext): string {
  if (r.source === "change") return auditSearchHaystack(ctx.t, r.entry);
  if (r.source === "call") return callHaystack(r.call, ctx);
  return daemonSearchHaystack(ctx.t, r.log);
}

/** The daemon logger a record names, if any. */
export function recordLogger(r: ActivityRecord): string {
  if (r.source !== "daemon") return "";
  const logger = r.log.record?.logger;
  return typeof logger === "string" ? logger : "";
}

/** Whether a change was made by the agent `uid` (its actor names the agent). */
function changeByAgent(entry: AuditEntry, uid: string, ctx: FilterContext): boolean {
  const name = ctx.agentNames.get(uid);
  return entry.actor === uid || (name !== undefined && entry.actor === name);
}

/**
 * The client-side half of the filters: what the routes cannot narrow by
 * themselves (free text, the custom range's upper bound, a change's who and
 * server, a kind, a logger). The server-side half — time window, a call's
 * server, agent and status, the daemon's level floor — is in the request.
 */
export function matchesFilters(
  r: ActivityRecord,
  tab: ActivityTab,
  f: ActivityFilters,
  ctx: FilterContext,
): boolean {
  if (ctx.until && r.at && timeMs(r.at) > timeMs(ctx.until)) return false;
  if (f.by !== "any") {
    if (f.by.startsWith("agent:")) {
      const uid = f.by.slice("agent:".length);
      if (r.source === "call" && r.call.agent_uid !== uid) return false;
      if (r.source === "change" && !changeByAgent(r.entry, uid, ctx)) return false;
      if (r.source === "daemon") return false;
    } else {
      const actor = f.by.slice("actor:".length);
      if (r.source === "call") return false;
      const made = r.source === "change" ? r.entry.actor : "";
      if (
        r.source === "change" &&
        made !== actor &&
        !(actor === "system" && made.startsWith("system:"))
      ) {
        return false;
      }
      if (r.source === "daemon" && actor !== "system") return false;
    }
  }
  if (f.server !== "any") {
    if (r.source === "daemon") return false;
    if (r.source === "call" && r.call.resource_uid !== f.server) return false;
    if (r.source === "change") {
      const name = ctx.serverNames.get(f.server);
      if (r.entry.resource_kind !== "mcp_server" || r.entry.resource_name !== name) return false;
    }
  }
  if ((tab === "everything" || tab === "changes") && f.kind.startsWith("change:")) {
    if (r.source !== "change" || r.entry.resource_kind !== f.kind.slice("change:".length)) {
      return false;
    }
  }
  if (tab === "daemon" && f.logger !== "any" && recordLogger(r) !== f.logger) return false;
  const query = f.search.trim().toLowerCase();
  if (query && !recordHaystack(r, ctx).includes(query)) return false;
  return true;
}

// ---------------------------------------------------------------------------
// What a row says about itself
// ---------------------------------------------------------------------------

/** A call that did not succeed. */
export function callFailed(call: Invocation): boolean {
  return call.status !== "ok";
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
