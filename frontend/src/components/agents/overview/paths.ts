// src/components/agents/overview/paths.ts — the files the Overview names: where each Coffer part lives.
//
// Claude Code keeps its MCP servers in `.claude.json` beside the config
// directory when that directory is the standard `~/.claude` (so the file is
// `~/.claude.json`), and inside the directory otherwise; its hooks sit in
// `settings.json`. Codex keeps both in its directory: `config.toml` and
// `hooks.json`. Cursor, OpenCode and DeepSeek Harness keep their MCP entries
// in `mcp.json`, `opencode.json` and `cordis.patch.yml` inside their
// directories. Paths come back home-relative, as the board prints them.
import { abbreviateHomePath } from "@/lib/agents/display";
import { connectionFiles } from "@/lib/agents/connectionPlan";
import type { AgentOut, AgentTypeOut } from "@/lib/api/agents";

function join(dir: string, file: string): string {
  return `${dir.replace(/[\\/]+$/, "")}/${file}`;
}

/** The last segment of a path. */
export function baseName(path: string): string {
  return (
    path
      .split(/[\\/]+/)
      .filter(Boolean)
      .pop() ?? path
  );
}

/** The file that holds the agent's MCP entries (Coffer's `coffer` entry among them). */
export function mcpConfigPath(
  agent: Pick<AgentOut, "type" | "config_dir">,
  typeRow: Pick<AgentTypeOut, "standard_config_dir">,
): string {
  return abbreviateHomePath(
    connectionFiles({
      type: agent.type,
      config_dir: agent.config_dir,
      standard_config_dir: typeRow.standard_config_dir,
      state: "installed_active",
    }).mcp,
  );
}

const MAIN_FILE: Partial<Record<string, string>> = {
  codex: "config.toml",
  antigravity: "mcp_config.json",
  cursor: "cli-config.json",
  opencode: "opencode.json",
  deepseek_harness: "cordis.patch.yml",
};

/** The file whose absence means the agent is gone from its directory. */
export function mainConfigPath(agent: Pick<AgentOut, "type" | "config_dir">): string {
  const file = MAIN_FILE[agent.type] ?? "settings.json";
  return abbreviateHomePath(join(agent.config_dir, file));
}
