// src/lib/activity/filters.ts — Activity's filters: their state, which logs a tab reads under them, and the client-side predicate.
//
// The server-side half of a filter (time window, free text, a single agent and
// status, the daemon's level floor) travels in each log's request
// (`useActivityFeed.sourceParams`); this module is the half the routes cannot
// apply and the rules both halves share. Pure functions only.
//
// By and Kind are multi-select (design 6.2.04, 6.2.05): a record passes when
// it matches any of the chosen values, and choosing none is "Any". There is no
// server filter: the search matches a server's name.
import type { TFunction } from "i18next";

import {
  TAB_SOURCES,
  recordLogger,
  recordTimeMs,
  type ActivityRecord,
  type ActivitySource,
  type ActivityTab,
  type AuditEntry,
} from "./records";

/**
 * What a change is about, in the order the kind filter lists them. A resource
 * kind when the change names a resource; otherwise the area its event belongs
 * to — secrets, sync, CLIs, or Coffer's own settings.
 */
export const CHANGE_CATEGORIES = [
  "mcp_server",
  "skill",
  "agent",
  "provider",
  "channel",
  "secret",
  "sync",
  "settings",
  "knowledge",
  "memory",
  "cli",
] as const;
export type ChangeCategory = (typeof CHANGE_CATEGORIES)[number];

const EVENT_AREAS: [RegExp, ChangeCategory][] = [
  [/^(secret_|master_key_)/, "secret"],
  [/^sync_/, "sync"],
  [/^memory_/, "memory"],
  [/^knowledge_/, "knowledge"],
  [/^skill_/, "skill"],
  [/^agent_/, "agent"],
  [/^provider_/, "provider"],
  [/^channel_/, "channel"],
  [/^cli_/, "cli"],
];

/** The kind-filter category one change falls under. */
export function changeCategory(entry: AuditEntry): ChangeCategory {
  const kind = entry.resource_kind;
  if (kind && (CHANGE_CATEGORIES as readonly string[]).includes(kind)) {
    return kind as ChangeCategory;
  }
  for (const [pattern, area] of EVENT_AREAS) if (pattern.test(entry.event_type)) return area;
  // Everything else Coffer records without a resource is a change to its own
  // settings: the access token, retention, residency, Coffer's model, the cache.
  return "settings";
}

/** Who a change was made by when it was not an agent, as the who filter groups them. */
export const WHO_ACTORS = ["you", "cli", "system", "sync"] as const;

/**
 * The who-group an audit actor falls under, or null when the actor names an
 * agent. The web UI, the desktop app and a user action are all "you"; every
 * background pass of the daemon (`system:<worker>`) is Coffer.
 */
function actorWho(actor: string): string | null {
  if (actor === "ui" || actor === "user" || actor === "desktop") return "you";
  if (actor === "system" || actor.startsWith("system:")) return "system";
  if (actor === "cli" || actor === "sync" || actor === "api" || actor === "channel") return actor;
  return null;
}

/** The Everything tab's kinds: the three records, flat. */
export const RECORD_KINDS = ["calls", "changes", "daemon"] as const;

/** An MCP call status filter: all, ok, or every failure (error, timeout, denied). */
export type StatusFilter = "all" | "ok" | "failed";

/** @ui-only Every Activity filter; each tab reads the ones its records afford. */
export interface ActivityFilters {
  /** The time range as the URL carries it: a preset id or a custom range. */
  range: string;
  /** Free text; each log's route applies it (debounced, one request per pause in typing). */
  search: string;
  /** By: `agent:<uid>` and `actor:<who group>` values; empty is any. */
  by: string[];
  /**
   * Kind: on Everything "calls", "changes" and "daemon"; on Changes the change
   * categories. Empty is any.
   */
  kinds: string[];
  /** An MCP call's outcome (Tool calls tab). */
  status: StatusFilter;
  /** Daemon log severity floor; "" is every level (Daemon log tab). */
  level: "" | "info" | "warning" | "error";
  /** A daemon logger name (Daemon log tab); null is any. */
  logger: string | null;
}

export const DEFAULT_FILTERS: ActivityFilters = {
  range: "1h",
  search: "",
  by: [],
  kinds: [],
  status: "all",
  level: "",
  logger: null,
};

/** The time range a tab opens on until the reader picks one: the daemon log is sparser. */
export function defaultRange(tab: ActivityTab): string {
  return tab === "daemon" ? "24h" : DEFAULT_FILTERS.range;
}

/** The who values a tab applies: calls only have agents; the daemon log has no who. */
function byFor(tab: ActivityTab, f: ActivityFilters): string[] {
  if (tab === "daemon") return [];
  if (tab === "mcp") return f.by.filter((b) => b.startsWith("agent:"));
  return f.by;
}

/** The kind values a tab applies: Everything the three records, Changes its categories. */
function kindsFor(tab: ActivityTab, f: ActivityFilters): string[] {
  if (tab === "everything")
    return f.kinds.filter((k) => (RECORD_KINDS as readonly string[]).includes(k));
  if (tab === "changes") {
    return f.kinds.filter((k) => (CHANGE_CATEGORIES as readonly string[]).includes(k));
  }
  return [];
}

/** The one agent the who filter names, when it names exactly one and nothing else. */
export function singleAgent(tab: ActivityTab, f: ActivityFilters): string | undefined {
  const by = byFor(tab, f);
  return by.length === 1 && by[0].startsWith("agent:") ? by[0].slice("agent:".length) : undefined;
}

/** Whether anything narrows the view beyond the time range: what "Clear filters" resets. */
export function filtersNarrow(f: ActivityFilters, tab: ActivityTab): boolean {
  if (f.search.trim() || byFor(tab, f).length || kindsFor(tab, f).length) return true;
  if (tab === "mcp" && f.status !== "all") return true;
  if (tab === "daemon" && (f.level !== "" || f.logger !== null)) return true;
  return false;
}

/**
 * Whether the totals the logs report still describe what is shown: a who
 * beyond one agent and a logger are applied on the client, so "of M" would
 * count records the filter hides.
 */
export function totalsExact(f: ActivityFilters, tab: ActivityTab): boolean {
  const by = byFor(tab, f);
  if (by.length > 0 && singleAgent(tab, f) === undefined) return false;
  return !(tab === "daemon" && f.logger !== null);
}

/**
 * The sources a tab reads once its filters are applied: a kind or a who that
 * only one or two logs can carry drops the others, so they are not fetched.
 */
export function sourcesFor(tab: ActivityTab, f: ActivityFilters): ActivitySource[] {
  let sources = [...TAB_SOURCES[tab]];
  const kinds = kindsFor(tab, f);
  if (tab === "everything" && kinds.length) {
    sources = sources.filter((s) =>
      s === "call"
        ? kinds.includes("calls")
        : s === "daemon"
          ? kinds.includes("daemon")
          : kinds.includes("changes"),
    );
  }
  const by = byFor(tab, f);
  if (by.length) {
    const agents = by.some((b) => b.startsWith("agent:"));
    const coffer = by.includes("actor:system");
    sources = sources.filter(
      (s) => s === "change" || (s === "call" && agents) || (s === "daemon" && coffer),
    );
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
}

/** The agent uid a change was made by, when its actor names one. */
function changeAgent(entry: AuditEntry, agentNames: ReadonlyMap<string, string>): string | null {
  if (actorWho(entry.actor) !== null) return null;
  if (agentNames.has(entry.actor)) return entry.actor;
  for (const [uid, name] of agentNames) if (name === entry.actor) return uid;
  return null;
}

/** The who value one record carries — `agent:<uid>` or `actor:<group>` — or null. */
function recordWho(r: ActivityRecord, agentNames: ReadonlyMap<string, string>): string | null {
  if (r.source === "call") return r.call.agent_uid ? `agent:${r.call.agent_uid}` : null;
  if (r.source === "daemon") return "actor:system";
  const who = actorWho(r.entry.actor);
  if (who) return `actor:${who}`;
  const uid = changeAgent(r.entry, agentNames);
  return uid ? `agent:${uid}` : null;
}

/** The Everything kind value one record carries: "calls", "changes" or "daemon". */
function recordKind(r: ActivityRecord): string {
  if (r.source === "call") return "calls";
  if (r.source === "daemon") return "daemon";
  return "changes";
}

/**
 * The client-side half of the filters: what the routes cannot narrow by
 * themselves (the custom range's upper bound, who beyond one agent, a change's
 * category, a logger). The server-side half — the time window, the free text,
 * a single agent and status, the daemon's level floor — is in the request, so
 * a page of results is the first page of what matches.
 */
export function matchesFilters(
  r: ActivityRecord,
  tab: ActivityTab,
  f: ActivityFilters,
  ctx: FilterContext,
): boolean {
  if (ctx.until && r.at && recordTimeMs(r.at) > recordTimeMs(ctx.until)) return false;
  const by = byFor(tab, f);
  if (by.length) {
    const who = recordWho(r, ctx.agentNames);
    if (!who || !by.includes(who)) return false;
  }
  const kinds = kindsFor(tab, f);
  if (kinds.length) {
    if (tab === "changes") {
      if (r.source !== "change" || !kinds.includes(changeCategory(r.entry))) return false;
    } else if (!kinds.includes(recordKind(r))) return false;
  }
  if (tab === "daemon" && f.logger !== null && recordLogger(r) !== f.logger) return false;
  return true;
}
