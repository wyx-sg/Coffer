// src/lib/conversations/filters.test.ts
import { describe, expect, it } from "vitest";

import type { Conversation } from "@/lib/api/chat";
import {
  clearFilters,
  filterConversations,
  filtersSearch,
  hasLegacyChannel,
  isFiltered,
  parseFilters,
  sourceToken,
} from "./filters";

function conv(id: string, agent: string, binding?: Partial<Conversation["channel_binding"]>) {
  return {
    id,
    agent_key: agent,
    title: id,
    created_at: "2026-09-30T08:00:00Z",
    updated_at: "2026-09-30T08:00:00Z",
    archived_at: null,
    running: false,
    preview: null,
    channel_binding: binding
      ? {
          channel_uid: "ch1",
          channel: "Team bot",
          chat_id: "c1",
          mirror: null,
          platform: "seatalk",
          place: null,
          ...binding,
        }
      : null,
  } as Conversation;
}

const web = conv("web", "claude_code");
const seatalk = conv("st", "claude_code", {});
const telegram = conv("tg", "codex", { channel_uid: "ch2", platform: "telegram" });
const orphan = conv("gone", "codex", { channel_uid: "ch3", channel: null, platform: null });
const all = [web, seatalk, telegram, orphan];

describe("conversation filters", () => {
  it("reads sources, agents, the search and the archived view from the URL", () => {
    expect(
      parseFilters(new URLSearchParams("source=coffer,ch2&agent=codex&archived=1&q=sentry")),
    ).toEqual({ source: ["coffer", "ch2"], agent: ["codex"], archived: true, q: "sentry" });
    expect(parseFilters(new URLSearchParams(""))).toEqual({
      source: [],
      agent: [],
      archived: false,
      q: "",
    });
  });

  it("round-trips through the URL, writing only what narrows the list", () => {
    expect(filtersSearch(parseFilters(new URLSearchParams("")))).toBe("");
    const f = { source: ["coffer", "ch1"], agent: ["codex"], archived: true, q: "a b" };
    expect(filtersSearch(f)).toBe("?source=coffer,ch1&agent=codex&archived=1&q=a+b");
    expect(parseFilters(new URLSearchParams(filtersSearch(f)))).toEqual(f);
  });

  it("reads a legacy ?channel=<uid> as one source", () => {
    const params = new URLSearchParams("channel=ch1&agent=codex");
    expect(hasLegacyChannel(params)).toBe(true);
    const f = parseFilters(params);
    expect(f.source).toEqual(["ch1"]);
    // Written back, the legacy key is gone.
    expect(filtersSearch(f)).toBe("?source=ch1&agent=codex");
    expect(hasLegacyChannel(new URLSearchParams(filtersSearch(f)))).toBe(false);
    expect(parseFilters(new URLSearchParams("source=ch1&channel=ch1")).source).toEqual(["ch1"]);
  });

  it("filters by source (several at once) and by agent", () => {
    const by = (q: string) => filterConversations(all, parseFilters(new URLSearchParams(q)));
    expect(by("source=coffer")).toEqual([web]);
    expect(by("source=ch1")).toEqual([seatalk]);
    expect(by("source=coffer,ch2")).toEqual([web, telegram]);
    expect(by("agent=codex")).toEqual([telegram, orphan]);
    expect(by("agent=codex&source=ch2,ch3")).toEqual([telegram, orphan]);
    expect(by("")).toEqual(all);
  });

  it("names a conversation's source by its channel uid, Coffer when it has none", () => {
    expect(sourceToken(orphan)).toBe("ch3");
    expect(sourceToken(web)).toBe("coffer");
  });

  it("counts a source, an agent or a search as narrowing, and clears them but not the archived view", () => {
    const base = parseFilters(new URLSearchParams("archived=1"));
    expect(isFiltered(base)).toBe(false);
    expect(isFiltered({ ...base, q: "  " })).toBe(false);
    const narrowed = { ...base, source: ["ch1"], agent: ["codex"], q: "x" };
    expect(isFiltered(narrowed)).toBe(true);
    expect(clearFilters(narrowed)).toEqual(base);
  });
});
