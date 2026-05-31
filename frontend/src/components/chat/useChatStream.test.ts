// frontend/src/components/chat/useChatStream.test.ts
//
// Pure-helper coverage for the live-turn projection: liveTurnMessages() turns
// the streaming overlay state into the synthetic user / assistant rows the
// transcript renders on top of persisted history, and summarizeArgs() builds
// the compact tool-arg preview.
import { describe, expect, test } from "vitest";

import { liveTurnMessages, summarizeArgs } from "./useChatStream";

const BASE = {
  pendingUserText: null,
  assistantText: "",
  toolCalls: [],
  confirmation: null,
  streaming: false,
  error: null,
};

describe("liveTurnMessages", () => {
  test("returns no rows when idle", () => {
    expect(liveTurnMessages(BASE)).toEqual([]);
  });

  test("emits a user row plus a streaming assistant row mid-turn", () => {
    const rows = liveTurnMessages({
      ...BASE,
      pendingUserText: "hello",
      assistantText: "hi ",
      streaming: true,
    });
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ role: "user", content: "hello" });
    expect(rows[1]).toMatchObject({ role: "assistant", content: "hi ", status: "streaming" });
  });

  test("projects tool calls onto the assistant row with an args summary", () => {
    const rows = liveTurnMessages({
      ...BASE,
      pendingUserText: "go",
      streaming: true,
      toolCalls: [{ id: "t1", tool: "shell", args: { cmd: "ls" }, ok: true, summary: "done" }],
    });
    const assistant = rows[1];
    expect(assistant.tool_calls).toHaveLength(1);
    expect(assistant.tool_calls[0]).toMatchObject({
      id: "t1",
      tool: "shell",
      result_summary: "done",
    });
    expect(assistant.tool_calls[0].args_summary).toContain("ls");
  });

  test("marks the assistant row failed and carries the error when a turn errors", () => {
    const rows = liveTurnMessages({
      ...BASE,
      pendingUserText: "go",
      streaming: false,
      error: { code: "BOOM", message: "kaboom" },
    });
    const assistant = rows[rows.length - 1];
    expect(assistant.status).toBe("failed");
    expect(assistant.error).toMatchObject({ code: "BOOM", message: "kaboom" });
  });
});

describe("summarizeArgs", () => {
  test("serialises a small object", () => {
    expect(summarizeArgs({ a: 1, b: "x" })).toBe('{"a":1,"b":"x"}');
  });

  test("truncates a long object with an ellipsis", () => {
    const big = { v: "x".repeat(500) };
    const out = summarizeArgs(big);
    expect(out.length).toBeLessThanOrEqual(201);
    expect(out.endsWith("…")).toBe(true);
  });
});
