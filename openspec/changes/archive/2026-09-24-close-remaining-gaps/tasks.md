## 1. CLI parity

- [x] 1.1 `coffer sync remote set --worktree <path>` keeps the stored tree when omitted and surfaces the refusal of a tree inside the vault
- [x] 1.2 `coffer mcp invocations [<server>]` reads every server when none is named
- [x] 1.3 `coffer skill files|cat|write` over the skill file routes, with the fingerprint and the builtin refusal
- [x] 1.4 `coffer engine upkeep runs [--json]`
- [x] 1.5 Parity table in `test_cli_parity.py`; Purpose gap sentences removed

## 2. An agent's own config directory

- [x] 2.1 Claude Code's `.claude.json` resolves inside a custom config dir (probed against Claude Code 2.1.281); allowlist, MCP install, MCP entries and model discovery share one resolver
- [x] 2.2 Turns, the Codex `model/list` probe and Claude Code plugin uninstall carry `CLAUDE_CONFIG_DIR` / `CODEX_HOME` for a custom dir
- [x] 2.3 Contract descriptions name the agent's own global config file; regenerate the client

## 3. Sync

- [x] 3.1 Internal-engine default tie-break by uid; a two-vault round test proves convergence
- [x] 3.2 No master key → every ciphertext ref reported locked; unreadable key → none, logged; key resolved once

## 4. Close

- [x] 4.1 Every new scenario's test carries its acceptance marker
- [x] 4.2 Run `make verify`
- [x] 4.3 Archive the change
