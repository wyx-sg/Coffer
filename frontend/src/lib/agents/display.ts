// frontend/src/lib/agents/display.ts — human-readable forms of agent wire values.
// The daemon speaks in registry keys (`claude_code`) and absolute paths; the UI
// shows a product name and a home-relative path. Kept as pure functions so the
// table, the add form and the detail header all render the same label.
import type { AgentType } from "@/lib/api/agents";

const AGENT_TYPE_LABELS: Record<AgentType, string> = {
  claude_code: "Claude Code",
  codex: "Codex",
  antigravity: "Antigravity",
  cursor: "Cursor",
  opencode: "OpenCode",
  deepseek_harness: "DeepSeek Harness",
};

/** Product name for an agent type key; unknown keys fall through unchanged. */
export function agentTypeLabel(type: string): string {
  return AGENT_TYPE_LABELS[type as AgentType] ?? type;
}

/** What a person reads for an agent: its display name, else its type's product name, else its key. */
export function agentDisplayName(agent: {
  type?: string | null;
  name: string;
  display_name?: string;
}): string {
  return agent.display_name || (agent.type ? agentTypeLabel(agent.type) : agent.name);
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

/** The program an agent type runs as, as it appears on PATH. */
export function agentProgramName(type: AgentType): string {
  return AGENT_PROGRAMS[type];
}

const AGENT_PROGRAMS: Record<AgentType, string> = {
  claude_code: "claude",
  codex: "codex",
  antigravity: "agy",
  cursor: "cursor-agent",
  opencode: "opencode",
  deepseek_harness: "dsh",
};

/** How each agent's own terminal interface resumes a session (`{id}` is the
 *  session id); a type without one is absent. Mirrors the daemon's
 *  `AGENT_PROGRAMS` (backend/coffer/application/fs/terminal_command.py). */
const TERMINAL_RESUME: Partial<Record<AgentType, string>> = {
  claude_code: "--resume {id}",
  codex: "resume {id}",
  cursor: "--resume {id}",
  opencode: "--session {id}",
};

/** Whether Coffer can open the agent type's sessions in a terminal. */
export function opensInTerminal(type: string | null | undefined): type is AgentType {
  return !!type && type in TERMINAL_RESUME;
}

/** `<program> <resume args>` for a session of `type`, the id as given. */
export function terminalResume(type: AgentType, id: string): string {
  const args = TERMINAL_RESUME[type] ?? "";
  return `${agentProgramName(type)} ${args.replace("{id}", id)}`.trim();
}

/** What an agent's own command can do to one of its sessions. Claude Code and
 *  Codex rename and delete; OpenCode only deletes (`opencode session delete`);
 *  DeepSeek Harness and Cursor can do neither from their command lines. */
const SESSION_ACTIONS: Record<AgentType, { rename: boolean; delete: boolean }> = {
  claude_code: { rename: true, delete: true },
  codex: { rename: true, delete: true },
  antigravity: { rename: false, delete: false },
  cursor: { rename: false, delete: false },
  opencode: { rename: false, delete: true },
  deepseek_harness: { rename: false, delete: false },
};

export function sessionActions(type: string | null | undefined): {
  rename: boolean;
  delete: boolean;
} {
  return type && type in SESSION_ACTIONS
    ? SESSION_ACTIONS[type as AgentType]
    : { rename: true, delete: true };
}

/** Where the agent type keeps its sessions, for the empty Sessions tab. */
export function sessionStore(type: AgentType, configDir: string): string {
  const dir = abbreviateHomePath(configDir);
  switch (type) {
    case "codex":
    case "deepseek_harness":
      return `${dir}/sessions`;
    case "cursor":
      return `${dir}/chats`;
    case "opencode":
      return "~/.local/share/opencode/opencode.db";
    default:
      return `${dir}/projects`;
  }
}
