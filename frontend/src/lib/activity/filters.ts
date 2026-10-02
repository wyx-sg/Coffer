// src/lib/activity/filters.ts — Activity's filters: their state, which logs a tab reads under them, and the client-side predicate.
//
// The server-side half of a filter (time window, free text, a call's server, a
// single agent and status, the daemon's level floor) travels in each log's request
// (`useActivityFeed.sourceParams`); this module is the half the routes cannot
// apply and the rules both halves share. Pure functions only.
//
// Who and Kind are multi-select (design 6.1.03, 6.1.04): a record passes when
// it matches any of the chosen values, and choosing none is "Any".
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

/** @ui-only Every Activity filter; each tab reads the ones its records afford. */
export interface ActivityFilters {
  /** A time preset key, or "custom" with from/to. */
  timeRange: string;
  from: string;
  to: string;
  /** Free text; each log's route applies it (debounced, one request per pause in typing). */
  search: string;
  /** Who: `agent:<uid>` and `actor:<who group>` values; empty is any. */
  by: string[];
  /** An MCP server's uid, or "any". */
  server: string;
  /** What: "calls", "daemon", "changes" (every change) and `change:<category>`; empty is any. */
  kinds: string[];
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
  by: [],
  server: "any",
  kinds: [],
  status: "any",
  level: "",
  logger: "any",
};

/** The who values a tab applies: calls only have agents; the daemon log has no who. */
function byFor(tab: ActivityTab, f: ActivityFilters): string[] {
  if (tab === "daemon") return [];
  if (tab === "mcp") return f.by.filter((b) => b.startsWith("agent:"));
  return f.by;
}

/** The kind values a tab applies: Everything all of them, Changes its categories. */
function kindsFor(tab: ActivityTab, f: ActivityFilters): string[] {
  if (tab === "everything") return f.kinds;
  if (tab === "changes") return f.kinds.filter((k) => k.startsWith("change:"));
  return [];
}

/** The one agent the who filter names, when it names exactly one and nothing else. */
export function singleAgent(tab: ActivityTab, f: ActivityFilters): string | undefined {
  const agents = byFor(tab, f).filter((b) => b.startsWith("agent:"));
  return agents.length === 1 ? agents[0].slice("agent:".length) : undefined;
}

/** Whether anything narrows the view beyond the default time window. */
export function filtersNarrow(f: ActivityFilters, tab: ActivityTab): boolean {
  if (f.search.trim() || byFor(tab, f).length || kindsFor(tab, f).length) return true;
  if (tab !== "daemon" && tab !== "changes" && f.server !== "any") return true;
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
  const kinds = kindsFor(tab, f);
  if (tab === "everything" && kinds.length) {
    sources = sources.filter((s) =>
      s === "call"
        ? kinds.includes("calls")
        : s === "daemon"
          ? kinds.includes("daemon")
          : kinds.some((k) => k === "changes" || k.startsWith("change:")),
    );
  }
  if (f.server !== "any") sources = sources.filter((s) => s !== "daemon");
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
  /** MCP server uid → name, for the server filter on changes. */
  serverNames: ReadonlyMap<string, string>;
}

/** The agent uid a change was made by, when its actor names one. */
function changeAgent(entry: AuditEntry, agentNames: ReadonlyMap<string, string>): string | null {
  if (actorWho(entry.actor) !== null) return null;
  if (agentNames.has(entry.actor)) return entry.actor;
  for (const [uid, name] of agentNames) if (name === entry.actor) return uid;
  return null;
}

/** The who value one record carries — `agent:<uid>` or `actor:<group>` — or null. */
export function recordWho(
  r: ActivityRecord,
  agentNames: ReadonlyMap<string, string>,
): string | null {
  if (r.source === "call") return r.call.agent_uid ? `agent:${r.call.agent_uid}` : null;
  if (r.source === "daemon") return "actor:system";
  const who = actorWho(r.entry.actor);
  if (who) return `actor:${who}`;
  const uid = changeAgent(r.entry, agentNames);
  return uid ? `agent:${uid}` : null;
}

/** The kind value one record carries: "calls", "daemon" or `change:<category>`. */
export function recordKind(r: ActivityRecord): string {
  if (r.source === "call") return "calls";
  if (r.source === "daemon") return "daemon";
  return `change:${changeCategory(r.entry)}`;
}

/** How many of `records` carry each value `of` gives them, for the pills' counts. */
export function tally(
  records: readonly ActivityRecord[],
  of: (r: ActivityRecord) => string | null,
): Map<string, number> {
  const out = new Map<string, number>();
  for (const r of records) {
    const value = of(r);
    if (value) out.set(value, (out.get(value) ?? 0) + 1);
  }
  return out;
}

/**
 * The client-side half of the filters: what the routes cannot narrow by
 * themselves (the custom range's upper bound, who, a change's server, the
 * kinds, a logger). The server-side half — the time window, the free text, a
 * call's server, a single agent and status, the daemon's level floor — is in
 * the request, so a page of results is the first page of what matches.
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
  if (f.server !== "any") {
    if (r.source === "daemon") return false;
    if (r.source === "call" && r.call.resource_uid !== f.server) return false;
    if (r.source === "change") {
      const name = ctx.serverNames.get(f.server);
      if (r.entry.resource_kind !== "mcp_server" || r.entry.resource_name !== name) return false;
    }
  }
  const kinds = kindsFor(tab, f);
  if (kinds.length) {
    const kind = recordKind(r);
    const allChanges = r.source === "change" && kinds.includes("changes");
    if (!allChanges && !kinds.includes(kind)) return false;
  }
  if (tab === "daemon" && f.logger !== "any" && recordLogger(r) !== f.logger) return false;
  return true;
}
