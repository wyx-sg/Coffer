// src/lib/conversations/filters.ts
// The Conversations page's filters (spec chat "Show channel conversations on
// the Conversations page"): the title-and-directory search, the channels and
// the agents, read from and written to the URL so a filtered list is a link
// (a channel's "Conversations from this channel" opens
// `/conversations?source=<uid>`). The server applies every one of them (the
// list asks for `source`, `agent` and `q` with each page); this module only
// reads and writes the URL.

export interface ConversationFilters {
  /** Channel uids; empty means every channel. */
  source: string[];
  /** Agent keys (`claude_code`, `codex`); empty means every agent. */
  agent: string[];
  /** The search text, matched against titles and working directories. */
  q: string;
}

const list = (raw: string | null): string[] =>
  Array.from(new Set((raw ?? "").split(",").filter(Boolean)));

export function parseFilters(params: URLSearchParams): ConversationFilters {
  const source = list(params.get("source"));
  // A link from before channels were a pill: `?channel=<uid>` is one source.
  const legacy = params.get("channel");
  if (legacy && !source.includes(legacy)) source.push(legacy);
  return { source, agent: list(params.get("agent")), q: params.get("q") ?? "" };
}

/** Whether the URL still spells a filter the old way (and should be rewritten once). */
export function hasLegacyChannel(params: URLSearchParams): boolean {
  return params.has("channel");
}

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

/** Whether anything narrows the list: a channel, an agent or a search. */
export function isFiltered(filters: ConversationFilters): boolean {
  return filters.source.length > 0 || filters.agent.length > 0 || filters.q.trim() !== "";
}

/** The same view with every filter cleared. */
export function clearFilters(): ConversationFilters {
  return { source: [], agent: [], q: "" };
}
