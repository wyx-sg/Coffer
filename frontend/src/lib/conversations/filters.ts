// src/lib/conversations/filters.ts
// The Conversations page's filters (spec chat "Show every conversation on the
// Conversations page"): the archived view, the title-and-message search, the
// sources (Coffer's own UI, or any number of channels) and the agents, read
// from and written to the URL so a filtered list is a link (a channel's
// "Conversations from this channel" opens `/conversations?source=<uid>`).
// Pure, so the matching is unit-tested alone.
import type { Conversation } from "@/lib/api/chat";

/** The source token for a conversation opened in Coffer's own UI; any other token is a channel uid. */
export const COFFER_SOURCE = "coffer";

export interface ConversationFilters {
  /** Source tokens — `coffer` and/or channel uids; empty means every source. */
  source: string[];
  /** Agent keys (`claude_code`, `codex`); empty means every agent. */
  agent: string[];
  /** The archived conversations instead of the active ones. */
  archived: boolean;
  /** The search text, matched against titles and message text. */
  q: string;
}

const list = (raw: string | null): string[] =>
  Array.from(new Set((raw ?? "").split(",").filter(Boolean)));

export function parseFilters(params: URLSearchParams): ConversationFilters {
  const source = list(params.get("source"));
  // A link from before sources were a pill: `?channel=<uid>` is one source.
  const legacy = params.get("channel");
  if (legacy && !source.includes(legacy)) source.push(legacy);
  return {
    source,
    agent: list(params.get("agent")),
    archived: params.get("archived") === "1",
    q: params.get("q") ?? "",
  };
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
  if (filters.archived) params.set("archived", "1");
  if (filters.q) params.set("q", filters.q);
  // Commas stay readable in the address bar.
  const s = params.toString().replace(/%2C/g, ",");
  return s ? `?${s}` : "";
}

/** The source token a conversation belongs to: `coffer`, or its channel's uid. */
export function sourceToken(conversation: Conversation): string {
  return conversation.channel_binding?.channel_uid ?? COFFER_SOURCE;
}

function matchesFilters(conversation: Conversation, filters: ConversationFilters): boolean {
  if (filters.agent.length > 0 && !filters.agent.includes(conversation.agent_key)) return false;
  if (filters.source.length === 0) return true;
  return filters.source.includes(sourceToken(conversation));
}

/** The pill filters applied to loaded rows (archived and the search are the server's). */
export function filterConversations(
  conversations: readonly Conversation[],
  filters: ConversationFilters,
): Conversation[] {
  return conversations.filter((c) => matchesFilters(c, filters));
}

/** Whether anything narrows the list: a source, an agent or a search (the archived view is a list, not a filter). */
export function isFiltered(filters: ConversationFilters): boolean {
  return filters.source.length > 0 || filters.agent.length > 0 || filters.q.trim() !== "";
}

/** The same view with every filter cleared (the archived view stays). */
export function clearFilters(filters: ConversationFilters): ConversationFilters {
  return { ...filters, source: [], agent: [], q: "" };
}

/** `values` with `value` added, or removed when already there. */
export function toggled(values: readonly string[], value: string): string[] {
  return values.includes(value) ? values.filter((v) => v !== value) : [...values, value];
}
