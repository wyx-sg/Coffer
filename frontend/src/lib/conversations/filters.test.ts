// src/lib/conversations/filters.test.ts
import { describe, expect, it } from "vitest";

import type { Conversation } from "@/lib/api/chat";
import { filterConversations, filtersSearch, parseFilters, sourceKey } from "./filters";

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
  it("reads a platform, a channel, an agent and the archived view from the URL", () => {
    expect(parseFilters(new URLSearchParams("source=seatalk&agent=codex&archived=1"))).toEqual({
      source: "seatalk",
      channel: null,
      agent: "codex",
      archived: true,
    });
    expect(parseFilters(new URLSearchParams("source=nope")).source).toBe("all");
  });

  it("writes only what narrows the list, a channel before its platform", () => {
    expect(filtersSearch(parseFilters(new URLSearchParams("")))).toBe("");
    expect(filtersSearch({ source: "seatalk", channel: "ch1", agent: null, archived: false })).toBe(
      "?channel=ch1",
    );
  });

  it("filters by source: Coffer, a platform, one channel", () => {
    const by = (q: string) => filterConversations(all, parseFilters(new URLSearchParams(q)));
    expect(by("source=coffer")).toEqual([web]);
    expect(by("source=seatalk")).toEqual([seatalk]);
    expect(by("source=telegram")).toEqual([telegram]);
    expect(by("channel=ch2")).toEqual([telegram]);
    expect(by("agent=codex")).toEqual([telegram, orphan]);
    expect(by("")).toEqual(all);
  });

  it("names a deleted channel's conversation by no platform", () => {
    expect(sourceKey(orphan)).toBe("channel");
    expect(sourceKey(web)).toBe("coffer");
  });
});
