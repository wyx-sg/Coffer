// frontend/src/lib/agents/display.ts — human-readable forms of agent wire values.
// The daemon speaks in registry keys (`claude_code`) and absolute paths; the UI
// shows a product name and a home-relative path. Kept as pure functions so the
// table, the add form and the detail header all render the same label.
import type { AgentType } from "@/lib/api/agents";

const AGENT_TYPE_LABELS: Record<AgentType, string> = {
  claude_code: "Claude Code",
  codex: "Codex",
};

/** Product name for an agent type key; unknown keys fall through unchanged. */
export function agentTypeLabel(type: string): string {
  return AGENT_TYPE_LABELS[type as AgentType] ?? type;
}

// A leading user-home segment on the three platforms the daemon runs on. The
// API returns absolute paths and does not expose the home directory, so the
// prefix is recognised by shape.
const HOME_PREFIX = /^(?:\/Users\/[^/]+|\/home\/[^/]+|[A-Za-z]:[\\/]Users[\\/][^\\/]+)(?=[\\/]|$)/;

/**
 * Shorten an absolute path for a table cell: `~/.claude` when it sits under a
 * home directory, otherwise the last two segments behind an ellipsis. The full
 * path belongs in a tooltip next to it.
 */
export function abbreviateHomePath(path: string): string {
  if (HOME_PREFIX.test(path)) return path.replace(HOME_PREFIX, "~");
  const parts = path.split(/[\\/]+/).filter(Boolean);
  if (parts.length <= 2) return path;
  return `…/${parts.slice(-2).join("/")}`;
}

// How each supported agent is installed (or reinstalled), for the rows and
// pages that say "not installed" or "config left behind": the command the user
// copies into a terminal. Coffer never runs it.
const INSTALL_COMMANDS: Record<AgentType, string> = {
  claude_code: "npm install -g @anthropic-ai/claude-code",
  codex: "npm install -g @openai/codex",
};

/** The command that installs (or reinstalls) an agent type's program. */
export function agentInstallCommand(type: AgentType): string {
  return INSTALL_COMMANDS[type];
}

/** The program an agent type runs as, as it appears on PATH. */
export function agentProgramName(type: AgentType): string {
  return type === "claude_code" ? "claude" : "codex";
}
