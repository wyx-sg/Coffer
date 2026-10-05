// src/lib/conversations/filters.ts
// The Conversations page's filters (spec chat "Show every agent's sessions on
// the Conversations page"): the title-and-directory search, the sources (`local`
// and channel uids) and the agents, read from and written to the URL so a
// filtered list is a link (a channel's "Conversations from this channel" opens
// `/conversations?source=<uid>`). The server applies every one of them (the
// list asks for `source`, `agent` and `q` with each page); this module only
// reads and writes the URL.

export interface ConversationFilters {
  /** `local` (this Mac) and channel uids; empty means every source. */
  source: string[];
  /** Agent keys (`claude_code`, `codex`); empty means every agent. */
  agent: string[];
  /** The search text, matched against titles and working directories. */
  q: string;
}

const list = (raw: string | null): string[] =>
  Array.from(new Set((raw ?? "").split(",").filter(Boolean)));

export function parseFilters(params: URLSearchParams): ConversationFilters {
  return {
    source: list(params.get("source")),
    agent: list(params.get("agent")),
    q: params.get("q") ?? "",
  };
}

/** The source value for sessions that were not started by a channel. */
export const LOCAL_SOURCE = "local";

/** The query string for `filters` — a default is never spelled out. */
export function filtersSearch(filters: ConversationFilters): string {
  const params = new URLSearchParams();
  if (filters.source.length > 0) params.set("source", filters.source.join(","));
  if (filters.agent.length > 0) params.set("agent", filters.agent.join(","));
  if (filters.q) params.set("q", filters.q);
  // Commas stay readable in the address bar.
  const s = params.toString().replace(/%2C/g, ",");
  return s ? `?${s}` : "";
}

/** Whether anything narrows the list: a source, an agent or a search. */
export function isFiltered(filters: ConversationFilters): boolean {
  return filters.source.length > 0 || filters.agent.length > 0 || filters.q.trim() !== "";
}

/** The same view with every filter cleared. */
export function clearFilters(): ConversationFilters {
  return { source: [], agent: [], q: "" };
}
