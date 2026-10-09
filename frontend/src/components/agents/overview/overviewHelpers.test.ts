// src/components/agents/overview/overviewHelpers.test.ts — where each Coffer part lives, and the short ages.
import { describe, expect, test } from "vitest";

import i18n from "@/i18n";

import { formatAgo } from "./age";
import { mainConfigPath, mcpConfigPath } from "./paths";

const t = i18n.getFixedT("en");
const STD = { standard_config_dir: "/Users/me/.claude" };

describe("paths", () => {
  test("Claude Code's MCP file sits beside the standard directory, inside a custom one", () => {
    expect(mcpConfigPath({ type: "claude_code", config_dir: "/Users/me/.claude" }, STD)).toBe(
      "~/.claude.json",
    );
    expect(mcpConfigPath({ type: "claude_code", config_dir: "/Users/me/work-claude" }, STD)).toBe(
      "~/work-claude/.claude.json",
    );
  });

  test("Codex keeps its MCP entry in its main config, in its directory", () => {
    const codex = { type: "codex" as const, config_dir: "/Users/me/.codex" };
    expect(mcpConfigPath(codex, STD)).toBe("~/.codex/config.toml");
    expect(mainConfigPath(codex)).toBe("~/.codex/config.toml");
  });
});

describe("age", () => {
  const now = Date.parse("2026-09-30T12:00:00Z");
  const ago = (ms: number) => new Date(now - ms).toISOString();

  test("one unit, rounded down", () => {
    expect(formatAgo(t, ago(30_000), now)).toBe("now");
    expect(formatAgo(t, ago(5 * 60_000), now)).toBe("5m");
    expect(formatAgo(t, ago(2 * 3600_000), now)).toBe("2h");
    expect(formatAgo(t, ago(3 * 86400_000), now)).toBe("3d");
    expect(formatAgo(t, ago(15 * 86400_000), now)).toBe("2w");
    expect(formatAgo(t, "not a time", now)).toBeNull();
  });
});
