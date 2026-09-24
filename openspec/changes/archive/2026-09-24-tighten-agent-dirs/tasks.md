## 1. Code

- [x] 1.1 Boot heal moves a custom-directory Claude Code agent's stale Coffer MCP entry from `~/.claude.json` into `<config_dir>/.claude.json`, backed up and audited
- [x] 1.2 The daemon clears inherited `CLAUDE_CONFIG_DIR` and `CODEX_HOME` at start and logs which it cleared
- [x] 1.3 The Codex model cache is keyed on the resolved config directory
- [x] 1.4 A test pins that the first enabled agent of a type in name order answers, and that a rename changes which one
- [x] 1.5 `coffer skill write` refuses empty content without `--allow-empty` and refuses a terminal stdin without `--from-file` (exit 2)
- [x] 1.6 `coffer skill cat` exits 1 on a truncated file unless `--json` is given
- [x] 1.7 A locked keychain at start creates no key and the daemon refuses to start with `CREDENTIAL_LOCKED`; no keychain backend reads as empty

## 2. Specs and docs

- [x] 2.1 Deltas for agent-registry, agent-registry/claude-code, chat, credentials, daemon and skill-manager
- [x] 2.2 Every new scenario's test carries its acceptance marker
- [x] 2.3 `docs-site/guide/agents.md`, `skills.md` and `credentials.md` describe the new behaviour

## 3. Close

- [x] 3.1 Run make verify
- [x] 3.2 Archive the change
