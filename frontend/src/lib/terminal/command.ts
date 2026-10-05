// src/lib/terminal/command.ts — the command line that resumes an agent session,
// for Copy command (spec chat "Open a conversation in the terminal"). The same
// line the daemon runs in the terminal it opens, so a person can run it anywhere.
import { agentProgramName } from "@/lib/agents/display";
import type { AgentType } from "@/lib/api/agents";

/** Wrap `value` in POSIX single quotes, escaping any quote inside it. */
export function shellQuote(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

const SAFE_ID = /^[A-Za-z0-9._-]+$/;

/**
 * `cd '<cwd>' && claude --resume <id>` for Claude Code, `cd '<cwd>' && codex resume <id>`
 * for Codex; without a working directory, just the resume command.
 */
export function resumeCommand(agent: AgentType, cwd: string | null, sessionId: string): string {
  const id = SAFE_ID.test(sessionId) ? sessionId : shellQuote(sessionId);
  const program = agentProgramName(agent);
  const resume = agent === "claude_code" ? `${program} --resume ${id}` : `${program} resume ${id}`;
  return cwd ? `cd ${shellQuote(cwd)} && ${resume}` : resume;
}
