## Why

The owner asked on 2026-11-19 for Coffer to support Cursor, OpenCode and DeepSeek Harness (`dsh`, DeepSeek's open-source agent) beside Claude Code and Codex, with as many features as each can take. Cursor and OpenCode were removed in PR #309 for being untestable; this change brings them back with a CI job that runs their real CLIs.

## What Changes

- Three new agent types, `cursor`, `opencode` and `deepseek_harness`, each a descriptor with its config directory, environment variable, program, install page, config-file allowlist and MCP injection.
- Two new MCP entry shapes: OpenCode's `local` entry with a command array (written in the 1.x shape; 1.x and 2.x entries listed), and a DeepSeek Harness Cordis patch row kept in a block Coffer marks inside `cordis.patch.yml`; the person's own rows there are listed but not removable (`MCP_ENTRY_NOT_EDITABLE`).
- YAML joins the config-file formats; a type may have no instructions file (Cursor).
- Skills: agents sharing one skills folder (`~/.agents/skills`) get one link per skill, placed when the skill reaches any of them.
- Agent and type rows carry `features`, derived from the descriptor and its facets; the Agents page shows only the tabs, tiles and sections a type has.
- A CI job (`agent-cli`) installs the real OpenCode 1.x and 2.x, DeepSeek Harness and Cursor CLIs and checks they read Coffer's entry.
- Not in this change: provider projection, drivers (chat, channels, scheduled tasks), sessions, plugins, hooks and memory for the new types.

## Capabilities

### New Capabilities

- `agent-registry/cursor`, `agent-registry/opencode`, `agent-registry/deepseek-harness`.

### Modified Capabilities

- `agent-registry`: five supported types; facets a type lacks are absent; `features` on agent and type rows; allowlists may hold YAML and at most one instructions file. Edited directly in the main spec, so this change carries no delta.
- `skills`: one link per shared skills folder.

## Impact

Backend agent domain (descriptor, types, allowlists, MCP install/entries, Cordis module, features), skill reconciler, agent routes and contracts, frontend Agents page, CI workflow and Makefile, ADRs `cursor-opencode-and-deepseek-harness-are-supported-agents`, `a-shared-skills-directory-holds-one-link-for-every-reader`, `deepseek-harness-mcp-row-lives-in-a-block-coffer-owns`, `opencode-gets-its-mcp-entry-in-the-1x-shape`, docs-site (en and zh).
