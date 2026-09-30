## 1. Shared

- [x] 1.1 `AttentionItem.handoff` and `AttentionItemOut.handoff`; `coffer attention --prompt <key>`
- [x] 1.2 `useAgentHandoff`; the Needs you row offers the hand-off in its ⋯ menu
- [x] 1.3 Required-command attention items carry their prompt; their reason names no command
- [x] 1.4 CLI refusals print `details.handoff.prompt`; `lib/api/errorHandoff.ts`
- [x] 1.5 `.agents/frontend.md` rule; docs-site architecture and web-ui guide

## 2. Agents and conversations

- [x] 2.1 Per-type install / reinstall prompt on `GET /agents/types` and `GET /agents/{uid}`; `coffer agent prompt`
- [x] 2.2 Remove `agentInstallCommand` and `InstallCommand`; rows, notices, detail and Overview cards show `AgentHandoff`
- [x] 2.3 Missing-program attention item carries the prompt
- [x] 2.4 Conversations with no managed agent offer the install prompt to copy, or a link to Agents
- [x] 2.5 `SHIM_NOT_FOUND` carries a prompt in its details; Connect shows it
- [x] 2.6 Plugin CLI and conversation providers look programs up on the agent's real `PATH`

## 3. MCP servers

- [x] 3.1 Launcher-missing prompt on status and attention; remove the Homebrew table
- [x] 3.2 Diagnose prompt (config summary with secrets redacted, stderr tail, error) beside Test and View log
- [x] 3.3 `coffer mcp handoff`, `coffer mcp test --prompt`

## 4. Skills and secrets

- [x] 4.1 Drift entries carry no remedy text; the UI says Repair puts it back; the CLI keeps its wording
- [x] 4.2 Prompts for a folder in the way, an orphan master and a missing master
- [x] 4.3 Merge-with-an-agent prompt on a conflicting update preview; `POST /skills/{uid}/source/merged`, `coffer skill update --merged`, audit `skill_update_merged`
- [x] 4.4 Git import with no git refused with a prompt; the add, change-source and update dialogs show it
- [x] 4.5 Plaintext-secret scan prompt, by file and line only

## 5. Channels, features, daemon

- [x] 5.1 SeaTalk `sdk_missing` prompt on channel status and attention; the banner shows it
- [x] 5.2 Feature gate Switch on, or the pin explained
- [x] 5.3 `POST /daemon/restart` with a successor; Restart in the browser; audit `daemon_restarted`
- [x] 5.4 `GET /daemon/upgrade` hand-off on Settings › About in a browser

## 6. Providers, usage, knowledge

- [x] 6.1 Local-runtime setup prompt when nothing answers; `coffer provider detect-local` prints it
- [x] 6.2 Statusline wrapper prompt on the quota card; `coffer usage quota --prompt`
- [x] 6.3 Refused pass undo carries a prompt for undoing it by hand
- [x] 6.4 Knowledge history with no git hands installing it to an agent

## 7. Verify

- [x] 7.1 Spec deltas, tests with acceptance markers, docs-site, en/zh, contracts and references regenerated
- [x] 7.2 `make verify`, `make verify-visual`
