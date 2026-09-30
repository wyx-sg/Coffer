// src/lib/agents/connectionPlan.test.ts — the files and lines a connection change previews.
import { describe, expect, test } from "vitest";

import { connectionFiles, planConnect, planDisconnect, type PlanAgent } from "./connectionPlan";

const OPTS = { placeholders: { uid: "<uid>", shim: "<shim>" } };

const claude: PlanAgent["row"] = {
  type: "claude_code",
  config_dir: "/Users/me/.claude",
  standard_config_dir: "/Users/me/.claude",
  state: "installed_active",
};
const codex: PlanAgent["row"] = {
  type: "codex",
  config_dir: "/Users/me/.codex",
  standard_config_dir: "/Users/me/.codex",
  state: "installed_active",
};

describe("connectionFiles", () => {
  test("Claude Code's entry sits in ~/.claude.json for the standard directory", () => {
    expect(connectionFiles(claude)).toEqual({
      mcp: "/Users/me/.claude.json",
      memory_hook: "/Users/me/.claude/settings.json",
    });
  });

  test("Claude Code's entry sits inside a custom directory", () => {
    const custom = { ...claude, config_dir: "/Users/me/work/claude-home" };
    expect(connectionFiles(custom).mcp).toBe("/Users/me/work/claude-home/.claude.json");
  });

  test("Codex writes config.toml and hooks.json in its directory", () => {
    expect(connectionFiles(codex)).toEqual({
      mcp: "/Users/me/.codex/config.toml",
      memory_hook: "/Users/me/.codex/hooks.json",
    });
  });
});

describe("planConnect", () => {
  test("an unregistered agent gets both parts, with placeholders for what is not known", () => {
    const items = planConnect([{ row: claude }, { row: codex }], OPTS);
    expect(items.map((i) => [i.id, i.path, i.op])).toEqual([
      ["claude_code:mcp", "~/.claude.json", "modify"],
      ["claude_code:memory_hook", "~/.claude/settings.json", "modify"],
      ["codex:mcp", "~/.codex/config.toml", "modify"],
      ["codex:memory_hook", "~/.codex/hooks.json", "modify"],
    ]);
    const entry = items[0].diff!.map((l) => l.text).join("\n");
    expect(entry).toContain('"command": "<shim>"');
    expect(entry).toContain('"--agent-uid", "<uid>"');
    expect(items[0].diff![0]).toEqual({ kind: "hunk", text: "mcpServers" });
    expect(items[0].added).toBe(4);
    expect(items[2].diff!.map((l) => l.text)).toContain("[mcp_servers.coffer]");
  });

  test("a never-run agent also gets its directory created", () => {
    const items = planConnect([{ row: { ...codex, state: "installed_never_run" } }], OPTS);
    expect(items[0]).toMatchObject({ id: "codex:dir", path: "~/.codex/", op: "add" });
    expect(items).toHaveLength(3);
  });

  test("a partial connection previews only the missing parts", () => {
    const items = planConnect(
      [
        {
          row: claude,
          uid: "agt_1",
          parts: [
            { key: "mcp", installed: true, detail: "/Users/me/.coffer/bin/coffer" },
            { key: "memory_hook", installed: false, detail: null },
          ],
        },
      ],
      OPTS,
    );
    expect(items.map((i) => i.id)).toEqual(["claude_code:memory_hook"]);
    expect(items[0].diff!.map((l) => l.text).join("\n")).toContain("--agent-uid agt_1");
  });

  test("a full connection plans nothing", () => {
    const parts = [
      { key: "mcp", installed: true, detail: "x" },
      { key: "memory_hook", installed: true, detail: "y" },
    ];
    expect(planConnect([{ row: claude, uid: "agt_1", parts }], OPTS)).toEqual([]);
  });
});

describe("planDisconnect", () => {
  test("removes each installed part with its installed command", () => {
    const items = planDisconnect(
      [
        {
          row: claude,
          uid: "agt_1",
          parts: [
            { key: "mcp", installed: true, detail: "/Users/me/.coffer/bin/coffer" },
            { key: "memory_hook", installed: false, detail: null },
          ],
        },
      ],
      OPTS,
    );
    expect(items).toHaveLength(1);
    expect(items[0].removed).toBe(4);
    expect(items[0].diff!.filter((l) => l.kind === "remove").map((l) => l.text)).toContain(
      '  "command": "/Users/me/.coffer/bin/coffer",',
    );
  });
});
