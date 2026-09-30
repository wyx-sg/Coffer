// src/lib/conversations/filters.ts
// The Conversations page's filters (spec chat "Show every conversation on the
// Conversations page"): by source — Coffer's own UI, a platform, or one
// channel — and by agent, read from and written to the URL so a filtered list
// is a link (a channel's "Conversations from this channel" opens
// `/conversations?channel=<uid>`). Pure, so the matching is unit-tested alone.
import type { Conversation } from "@/lib/api/chat";

/** Where a conversation came from: Coffer's own UI, or a channel's platform. */
export type SourceFilter = "all" | "coffer" | "seatalk" | "telegram";

export interface ConversationFilters {
  source: SourceFilter;
  /** One channel's uid — narrower than a platform, set by a channel's link. */
  channel: string | null;
  /** An agent key (`claude_code`, `codex`), or null for every agent. */
  agent: string | null;
  /** The archived conversations instead of the active ones. */
  archived: boolean;
}

const SOURCES: readonly SourceFilter[] = ["all", "coffer", "seatalk", "telegram"];

export function parseFilters(params: URLSearchParams): ConversationFilters {
  const raw = params.get("source") ?? "all";
  return {
    source: (SOURCES as readonly string[]).includes(raw) ? (raw as SourceFilter) : "all",
    channel: params.get("channel") || null,
    agent: params.get("agent") || null,
    archived: params.get("archived") === "1",
  };
}

/** The query string for `filters` — a default is never spelled out. */
export function filtersSearch(filters: ConversationFilters): string {
  const params = new URLSearchParams();
  if (filters.channel) params.set("channel", filters.channel);
  else if (filters.source !== "all") params.set("source", filters.source);
  if (filters.agent) params.set("agent", filters.agent);
  if (filters.archived) params.set("archived", "1");
  const s = params.toString();
  return s ? `?${s}` : "";
}

/** A channel conversation's platform key, "coffer" for one opened in Coffer, and
 *  "channel" for one whose channel has since been deleted. */
export function sourceKey(conversation: Conversation): string {
  const binding = conversation.channel_binding;
  if (!binding) return "coffer";
  return binding.platform ?? "channel";
}

function matchesFilters(conversation: Conversation, filters: ConversationFilters): boolean {
  if (filters.agent && conversation.agent_key !== filters.agent) return false;
  if (filters.channel) return conversation.channel_binding?.channel_uid === filters.channel;
  if (filters.source === "all") return true;
  return sourceKey(conversation) === filters.source;
}

export function filterConversations(
  conversations: readonly Conversation[],
  filters: ConversationFilters,
): Conversation[] {
  return conversations.filter((c) => matchesFilters(c, filters));
}

/** Whether any filter narrows the list (the archived view is a list, not a filter). */
export function isFiltered(filters: ConversationFilters): boolean {
  return filters.source !== "all" || filters.channel !== null || filters.agent !== null;
}
