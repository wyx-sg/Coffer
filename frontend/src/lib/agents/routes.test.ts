// src/lib/agents/routes.test.ts — the /agents addresses.
import { describe, expect, test } from "vitest";

import {
  AGENT_TABS,
  agentMemoryStorePath,
  agentSessionPath,
  agentTabPath,
  isAgentType,
  unmanagedSkillPath,
} from "./routes";

describe("agent addresses", () => {
  test("the eight tabs, in the page's order: six in the strip, two behind More", () => {
    expect(AGENT_TABS).toEqual([
      "overview",
      "skills",
      "mcp-servers",
      "hooks",
      "config",
      "sessions",
      "plugins",
      "memory",
    ]);
    expect(AGENT_TABS).not.toContain("model");
  });

  test("Overview is the bare address, every other tab a path segment", () => {
    expect(agentTabPath("claude_code", "overview")).toBe("/agents/claude_code");
    expect(agentTabPath("codex", "mcp-servers")).toBe("/agents/codex/mcp-servers");
    expect(agentTabPath("codex", "skills", "?owner=own")).toBe("/agents/codex/skills?owner=own");
  });

  test("pages opened from a tab are nested under it", () => {
    expect(unmanagedSkillPath("codex", "skills", "a b")).toBe(
      "/agents/codex/skills/unmanaged/skills/a%20b",
    );
    expect(agentMemoryStorePath("codex", "/h/.codex/memories", "Global")).toBe(
      "/agents/codex/memory/store?dir=%2Fh%2F.codex%2Fmemories&project=Global",
    );
    expect(agentSessionPath("codex", "/h/s.jsonl")).toBe(
      "/agents/codex/sessions?session=%2Fh%2Fs.jsonl",
    );
  });

  test("only the supported types are types", () => {
    expect(isAgentType("claude_code")).toBe(true);
    expect(isAgentType("codex")).toBe(true);
    expect(isAgentType("agt_01J8")).toBe(false);
    expect(isAgentType(undefined)).toBe(false);
  });
});
