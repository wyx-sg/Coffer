// frontend/src/lib/agents/display.test.ts
import { describe, expect, test } from "vitest";

import { abbreviateHomePath, agentTypeLabel } from "./display";

describe("agentTypeLabel", () => {
  test("maps registry keys to product names", () => {
    expect(agentTypeLabel("claude_code")).toBe("Claude Code");
    expect(agentTypeLabel("codex")).toBe("Codex");
  });

  test("passes an unknown key through unchanged", () => {
    expect(agentTypeLabel("mystery")).toBe("mystery");
  });
});

describe("abbreviateHomePath", () => {
  test("collapses a macOS or Linux home prefix to ~", () => {
    expect(abbreviateHomePath("/Users/yu/.claude")).toBe("~/.claude");
    expect(abbreviateHomePath("/home/u/.codex")).toBe("~/.codex");
    expect(abbreviateHomePath("/Users/yu")).toBe("~");
  });

  test("collapses a Windows home prefix to ~", () => {
    expect(abbreviateHomePath("C:\\Users\\yu\\.claude")).toBe("~\\.claude");
  });

  test("does not treat a lookalike as home", () => {
    // `/Usersx/...` and `/home` itself carry no user segment.
    expect(abbreviateHomePath("/Usersx/yu/.claude")).toBe("…/yu/.claude");
    expect(abbreviateHomePath("/home")).toBe("/home");
  });

  test("keeps the last two segments of a path outside home", () => {
    expect(abbreviateHomePath("/opt/agents/codex/config")).toBe("…/codex/config");
    expect(abbreviateHomePath("/etc/codex")).toBe("/etc/codex");
  });
});
