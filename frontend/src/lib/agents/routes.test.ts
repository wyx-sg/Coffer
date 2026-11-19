// src/lib/agents/routes.test.ts — the /agents addresses.
import { describe, expect, test } from "vitest";

import { AGENT_TABS, agentTabPath, isAgentType } from "./routes";

describe("agent addresses", () => {
  test("the seven tabs, in the page's order: six in the strip, one behind More", () => {
    expect(AGENT_TABS).toEqual([
      "overview",
      "skills",
      "mcp-servers",
      "hooks",
      "config",
      "sessions",
      "plugins",
    ]);
    expect(AGENT_TABS).not.toContain("model");
  });

  test("Overview is the bare address, every other tab a path segment", () => {
    expect(agentTabPath("claude_code", "overview")).toBe("/agents/claude_code");
    expect(agentTabPath("codex", "mcp-servers")).toBe("/agents/codex/mcp-servers");
    expect(agentTabPath("codex", "skills", "?owner=own")).toBe("/agents/codex/skills?owner=own");
  });

  test("only the supported types are types", () => {
    expect(isAgentType("claude_code")).toBe(true);
    expect(isAgentType("codex")).toBe(true);
    expect(isAgentType("agt_01J8")).toBe(false);
    expect(isAgentType(undefined)).toBe(false);
  });
});
