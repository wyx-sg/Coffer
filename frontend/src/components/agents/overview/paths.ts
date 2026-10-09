// src/components/agents/overview/paths.ts — the files the Overview names: where each Coffer part lives.
//
// Claude Code keeps its MCP servers in `.claude.json` beside the config
// directory when that directory is the standard `~/.claude` (so the file is
// `~/.claude.json`), and inside the directory otherwise; its hooks sit in
// `settings.json`. Codex keeps both in its directory: `config.toml` and
// `hooks.json`. Paths come back home-relative, as the board prints them.
import { abbreviateHomePath } from "@/lib/agents/display";
import type { AgentOut, AgentTypeOut } from "@/lib/api/agents";

function parentOf(path: string): string {
  const trimmed = path.replace(/[\\/]+$/, "");
  const i = trimmed.search(/[\\/][^\\/]*$/);
  return i <= 0 ? trimmed : trimmed.slice(0, i);
}

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
  if (agent.type === "codex") return abbreviateHomePath(join(agent.config_dir, "config.toml"));
  const dir =
    agent.config_dir === typeRow.standard_config_dir
      ? parentOf(agent.config_dir)
      : agent.config_dir;
  return abbreviateHomePath(join(dir, ".claude.json"));
}

/** The file whose absence means the agent is gone from its directory. */
export function mainConfigPath(agent: Pick<AgentOut, "type" | "config_dir">): string {
  const file = agent.type === "codex" ? "config.toml" : "settings.json";
  return abbreviateHomePath(join(agent.config_dir, file));
}
