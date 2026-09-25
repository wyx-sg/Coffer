// frontend/src/lib/chat/threadView.test.ts
import { describe, expect, test } from "vitest";

import type { Message } from "@/lib/api/chat";
import { retryTargetFor, textOf, visibleThreadMessages } from "./threadView";

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

const live = { blocks: [], streaming: true };

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

describe("retryTargetFor", () => {
  const png = { id: "a".repeat(32), filename: "shot.png", mime: "image/png" };

  test("prefers the optimistic echo, re-sending its text and its files' upload ids", () => {
    const echo = { id: "echo-1", text: "echoed", attachments: [png], sentAt: 0, afterSeq: -1 };
    expect(retryTargetFor([msg({})], echo)).toEqual({
      kind: "send",
      text: "echoed",
      attachments: [png],
    });
  });

  test("falls back to resending the last persisted user message by id, or nothing", () => {
    const rows = [
      msg({ id: "1", content: [{ type: "text", text: "first" }] }),
      msg({ id: "2", role: "assistant", content: [{ type: "text", text: "reply" }] }),
      msg({ id: "3", content: [{ type: "attachment", filename: "shot.png", mime: "image/png" }] }),
      msg({ id: "4", role: "assistant", status: "failed", content: [] }),
    ];
    expect(retryTargetFor(rows, undefined)).toEqual({ kind: "resend", messageId: "3" });
    expect(retryTargetFor([], undefined)).toBeNull();
  });
});
