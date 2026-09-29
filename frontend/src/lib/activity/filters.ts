// src/lib/activity/filters.ts — Activity's filters: their state, which logs a tab reads under them, and the client-side predicate.
//
// The server-side half of a filter (time window, a call's server, agent and
// status, the daemon's level floor) travels in each log's request
// (`useActivityFeed.sourceParams`); this module is the half the routes cannot
// apply and the rules both halves share. Pure functions only.
import type { TFunction } from "i18next";

import { auditSearchHaystack, daemonSearchHaystack } from "./activityText";
import {
  TAB_SOURCES,
  callServerLabel,
  recordLogger,
  recordTimeMs,
  type ActivityRecord,
  type ActivitySource,
  type ActivityTab,
  type AuditEntry,
  type Invocation,
} from "./records";

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
function recordHaystack(r: ActivityRecord, ctx: FilterContext): string {
  if (r.source === "change") return auditSearchHaystack(ctx.t, r.entry);
  if (r.source === "call") return callHaystack(r.call, ctx);
  return daemonSearchHaystack(ctx.t, r.log);
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
  if (ctx.until && r.at && recordTimeMs(r.at) > recordTimeMs(ctx.until)) return false;
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
