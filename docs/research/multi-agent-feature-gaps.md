# Multi-Agent Feature Gaps

How tools that manage or drive several coding agents (or models) say that a
feature does not apply to one of them, and how their surfaces show it.

Informs: spec `agent-registry` "Report what Coffer can do with each agent type",
spec `skill-manager` "Name the agents that also see a skill", ADR
[What Coffer Does for an Agent Follows From Its Facets](../decisions/what-coffer-does-for-an-agent-follows-from-its-facets.md).
Read 2026-11-19.

## Survey

| Product | How a gap is expressed | How surfaces show it |
| --- | --- | --- |
| Agent Client Protocol (Zed and others) | The agent declares `agentCapabilities` at `initialize` (`loadSession`, `promptCapabilities.image/audio/embeddedContext`, `mcpCapabilities.http/sse`, `session.*`). The spec: "Clients and Agents MUST treat all capabilities omitted in the `initialize` request as UNSUPPORTED." | The client offers an action only when the capability was declared, e.g. no "resume" without `loadSession`. |
| Rulesync (rules, MCP, commands, subagents, skills, hooks, permissions to about 60 tools) | One README matrix: rows are tools, columns features, a cell is ✅ or blank. "A ✅ means the feature is supported in at least one mode (project, global, or simulated)." | The matrix is the only place gaps are explained; per-mode detail on a separate reference page. |
| AgentsMesh (about 33 tools) | Four levels per cell: Native, Embedded, Partial, and "—": "Not supported. Feature is skipped for this target." | Project and global matrices; unsupported targets are skipped, not errors. |
| CC Switch (Claude Code, Codex, Gemini CLI, OpenCode, OpenClaw) | Each manual chapter names the apps it applies to: workspace and memory are OpenClaw only; the local proxy covers Claude, Codex and Gemini. | A feature appears only under the apps it applies to. |
| LiteLLM | A model-capability map (`supports_function_calling`, `supports_vision`, …) read through `get_model_info()`. | Callers query the data and decide; nothing hard-codes a model name. |
| VS Code extensions | `capabilities.untrustedWorkspaces.supported` is `true`, `false` or `"limited"` with a `description`. | Commands and menus that do not apply are hidden by `when` clauses; the description is shown once, on the extension's page. |
| Cursor | Reads `~/.agents/skills`, `~/.claude/skills` and `~/.codex/skills` as well as its own folder. The IDE has one switch to stop loading other tools' folders; the CLI has none and no per-skill switch (Cursor staff, forum thread 166558, 2026-07-29). | — |
| OpenCode | Reads `~/.claude/skills` and `~/.agents/skills` beside its own; a `permissions` rule with `"action": "skill"` and `"effect": "deny"` hides a skill by name. | — |

## Patterns

1. The integration declares what it can do; the surface does not guess, and an
   omitted capability means unsupported (ACP, LiteLLM, VS Code).
2. Entry points that do not apply are absent, not greyed out (VS Code `when`,
   CC Switch per-app chapters, ACP clients).
3. The explanation lives in one place: a matrix (Rulesync, AgentsMesh) or a
   details page (VS Code).
4. Graded support levels exist where a feature is translated into many target
   formats (AgentsMesh); tools that either do a thing or do not keep a binary.
5. Shared skills folders are read by several agents whatever a manager wants;
   only some agents offer a way to hide a skill (OpenCode), and Cursor's CLI
   offers none.

## Sources

- https://agentclientprotocol.com/protocol/initialization
- https://github.com/dyoshikawa/rulesync (README, "Supported Tools and Features")
- https://samplexbro.github.io/agentsmesh/reference/supported-tools
- https://cnb.cool/nfeyre/cc-switch-mirror/-/blob/main/docs/user-manual/en/README.md (v3.15.0)
- https://docs.litellm.ai/docs/provider_registration/add_model_pricing
- https://forum.cursor.com/t/no-way-to-opt-out-of-third-party-claude-code-codex-config-loading-the-flag-is-hardcoded/166558
- https://forum.cursor.com/t/toggle-or-allowlist-for-agent-skills-roots-stop-loading-claude-skills-and-codex-skills-when-i-only-want-cursor-agents/160199
- https://opencode.ai/docs/skills , https://opencode.ai/v2/docs/permissions/
