## Why

An agent's own skills, MCP servers and plugins could only be acted on one row at
a time. Adopting twenty hand-placed skills, or switching off a dozen plugins,
meant twenty dialogs.

## What Changes

- On the agent's Skills, MCP servers and Plugins tabs, the agent's own part
  gains row checkboxes and a select-all box. While rows are ticked a selection
  bar replaces the search row, reading "N of M selected" with Clear; Esc clears.
  Coffer's part is untouched.
- **Skills**: Adopt (unmanaged folders; one dialog with a shared reach, each
  skill keeping its folder name) and Delete….
- **MCP servers**: Adopt (entries that bypass Coffer, with default names and
  default secret references; the dialog says how many secret values move into
  the secret store) and Remove…. An entry of a file that does not parse takes no
  checkbox.
- **Plugins**: Enable and Disable (no confirmation, plugins already in that
  state are skipped and counted) and Uninstall… (disabled, with the reason,
  while the agent's program is missing).
- A bulk action sends the single-item request once per row, one after another,
  never stopping at the first failure. All done: one toast and the selection
  clears. Some failed: the failures are listed by name with Retry for just them.
  An action says how many selected rows it skips.

## Impact

- `frontend/src/components/agents/tabs/AgentKindTab.tsx`, `KindRow.tsx`; new
  `agents/bulk/`, `skills/useOwnSkillsBulk.tsx`, `mcp/useOwnMcpBulk.tsx`,
  `mcp/adoptBody.ts`, `useAgentPluginsBulk.tsx`, `lib/hooks/useBulkRun.ts`.
- Specs: agent-registry, skill-manager. No backend or wire change.
