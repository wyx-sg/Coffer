// frontend/src/lib/chat/threadView.test.ts
import { describe, expect, test } from "vitest";

import type { Message } from "@/lib/api/chat";
import { retryTextFor, textOf, visibleThreadMessages } from "./threadView";

const msg = (over: Partial<Message>): Message => ({
  id: "m",
  conversation_id: "c",
  seq: 1,
  role: "user",
  content: [{ type: "text", text: "hello" }],
  status: "complete",
  created_at: "",
  ...over,
});

const live = { text: "", toolBlocks: [], streaming: true };

describe("textOf", () => {
  test("joins text blocks and ignores the rest", () => {
    expect(
      textOf(
        msg({
          content: [
            { type: "text", text: "a" },
            { type: "attachment", filename: "f" },
            { type: "text", text: "b" },
          ],
        }),
      ),
    ).toBe("ab");
  });
});

describe("visibleThreadMessages", () => {
  const user = msg({ id: "u" });
  const placeholder = msg({ id: "p", role: "assistant", status: "streaming", content: [] });
  const partial = msg({
    id: "q",
    role: "assistant",
    status: "streaming",
    content: [{ type: "text", text: "so far" }],
  });

  test("keeps everything when idle", () => {
    expect(visibleThreadMessages([user, placeholder], null, null)).toEqual([user, placeholder]);
  });

  test("drops fetched streaming rows while the live bubble is shown", () => {
    expect(visibleThreadMessages([user, placeholder, partial], live, null)).toEqual([user]);
  });

  test("after a failed turn drops only the empty placeholder, never streamed text", () => {
    const out = visibleThreadMessages([user, placeholder, partial], null, new Error("x"));
    expect(out.map((m) => m.id)).toEqual(["u", "q"]);
  });
});

describe("retryTextFor", () => {
  test("prefers the optimistic echo", () => {
    expect(retryTextFor([msg({})], "echoed")).toBe("echoed");
  });

  test("falls back to the last persisted user message, or empty", () => {
    const rows = [
      msg({ id: "1", content: [{ type: "text", text: "first" }] }),
      msg({ id: "2", role: "assistant", content: [{ type: "text", text: "reply" }] }),
      msg({ id: "3", content: [{ type: "text", text: "last" }] }),
      msg({ id: "4", role: "assistant", status: "failed", content: [] }),
    ];
    expect(retryTextFor(rows, undefined)).toBe("last");
    expect(retryTextFor([], undefined)).toBe("");
  });
});
