// src/lib/agents/routes.test.ts — the /agents addresses and the redirects of the old ones.
import { describe, expect, test } from "vitest";

import {
  AGENT_TABS,
  agentMcpEntryPath,
  agentMemoryStorePath,
  agentPluginPath,
  agentSessionPath,
  agentTabPath,
  isAgentType,
  legacyAgentPath,
  unmanagedSkillPath,
} from "./routes";

describe("agent addresses", () => {
  test("the nine tabs, in the page's order", () => {
    expect(AGENT_TABS).toEqual([
      "overview",
      "model",
      "skills",
      "mcp-servers",
      "plugins",
      "hooks",
      "config",
      "memory",
      "sessions",
    ]);
  });

  test("Overview is the bare address, every other tab a path segment", () => {
    expect(agentTabPath("claude_code", "overview")).toBe("/agents/claude_code");
    expect(agentTabPath("codex", "mcp-servers")).toBe("/agents/codex/mcp-servers");
    expect(agentTabPath("codex", "skills", "?owner=own")).toBe("/agents/codex/skills?owner=own");
  });

  test("pages opened from a tab are nested under it", () => {
    expect(agentMcpEntryPath("codex", "gh", "config.toml")).toBe(
      "/agents/codex/mcp-servers/gh?source=config.toml",
    );
    expect(agentPluginPath("claude_code", "sp@market")).toBe(
      "/agents/claude_code/plugins/sp%40market",
    );
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

describe("old addresses", () => {
  test("old ?tab= values move to their path tab, other params kept", () => {
    expect(legacyAgentPath("codex", "", "?tab=mcpServers")).toBe("/agents/codex/mcp-servers");
    expect(legacyAgentPath("codex", "", "?tab=conversations&x=1")).toBe(
      "/agents/codex/sessions?x=1",
    );
  });

  test("the Conversations tab and its session page become Sessions", () => {
    expect(legacyAgentPath("codex", "/conversations", "")).toBe("/agents/codex/sessions");
    expect(legacyAgentPath("codex", "/conversations", "?path=%2Fa.jsonl")).toBe(
      "/agents/codex/sessions?session=%2Fa.jsonl",
    );
  });

  test("a memory store opened from the tab's own address moves under /memory/store", () => {
    expect(legacyAgentPath("codex", "/memory", "?dir=%2Fm&project=P")).toBe(
      "/agents/codex/memory/store?dir=%2Fm&project=P",
    );
  });

  test("current addresses are left alone (the path-tab ?tab= form is useDetailTab's)", () => {
    expect(legacyAgentPath("codex", "", "")).toBeNull();
    expect(legacyAgentPath("codex", "/skills", "?owner=own")).toBeNull();
    expect(legacyAgentPath("codex", "", "?tab=skills")).toBeNull();
    expect(legacyAgentPath("codex", "/memory", "")).toBeNull();
  });
});
