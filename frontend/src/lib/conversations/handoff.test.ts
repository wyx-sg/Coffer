// src/lib/conversations/handoff.test.ts — the draft hand-off's navigation and its state reader.
import { describe, expect, test, vi } from "vitest";

import { DRAFT_PATH, openHandoffDraft, readHandoffState } from "./handoff";

describe("readHandoffState", () => {
  test("reads a well-formed hand-off", () => {
    expect(
      readHandoffState({ handoff: { agentKey: "claude_code", cwd: "/w", prompt: "Install jq." } }),
    ).toEqual({ agentKey: "claude_code", cwd: "/w", prompt: "Install jq." });
  });

  test("a missing or blank folder is Coffer's own workspace", () => {
    expect(readHandoffState({ handoff: { agentKey: "codex", prompt: "p" } })?.cwd).toBeNull();
    expect(
      readHandoffState({ handoff: { agentKey: "codex", cwd: "", prompt: "p" } })?.cwd,
    ).toBeNull();
  });

  test.each([
    null,
    undefined,
    "text",
    {},
    { handoff: null },
    { handoff: "Install jq." },
    { handoff: { agentKey: "", prompt: "p" } },
    { handoff: { agentKey: "codex", prompt: "" } },
    { handoff: { agentKey: "codex", prompt: 3 } },
    { handoff: { agentKey: "codex", cwd: 1, prompt: "p" } },
  ])("anything else is no hand-off: %j", (state) => {
    expect(readHandoffState(state)).toBeNull();
  });
});

test("openHandoffDraft carries the prompt in the location state, not the URL", () => {
  const navigate = vi.fn();
  const handoff = { agentKey: "codex", cwd: null, prompt: "Install jq." };
  openHandoffDraft(navigate, handoff);
  expect(navigate).toHaveBeenCalledWith(DRAFT_PATH, { state: { handoff } });
  expect(DRAFT_PATH).toBe("/conversations/new");
});
