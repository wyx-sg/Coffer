## Why

A behaviour review of agent config directories and the commands around them
found places where Coffer's code or spec left a case open. An older Coffer
wrote a custom-directory Claude Code agent's MCP entry into `~/.claude.json`,
which Claude Code never reads for that directory. A daemon started from a shell
exporting `CLAUDE_CONFIG_DIR` or `CODEX_HOME` passed it to every agent it
spawned. The Codex model cache was not keyed on the directory it was read from.
Which agent answers for a type when two are registered was undefined in the
specs. `coffer skill write` saved empty content from a closed stdin and hung on
a terminal, and `coffer skill cat` exited 0 on a truncated read. A keychain
locked at daemon start let Coffer create a new file key that then hid the
keychain's key.

## What Changes

- agent-registry/claude-code: the first daemon start after upgrading moves a
  custom-directory agent's stale Coffer MCP entry from `~/.claude.json` into
  `<config_dir>/.claude.json`, backed up and audited, leaving every other entry
  alone.
- daemon: the daemon clears inherited `CLAUDE_CONFIG_DIR` and `CODEX_HOME` at
  start and logs which it cleared; an agent gets the variable only from its own
  registered directory.
- The Codex model cache is keyed on the resolved config directory, as the
  existing agent-registry/codex requirement already states, so one directory
  spelled two ways is probed once.
- agent-registry and chat: the agent that answers for a type is the first
  enabled one in name order, for chat turns and the model catalogue alike; the
  one-agent-per-directory requirement says two agents of one type on different
  directories are allowed.
- skill-manager: `coffer skill write` refuses empty content unless
  `--allow-empty` is given, and refuses up front when stdin is a terminal and
  `--from-file` is absent (exit 2). `coffer skill cat` exits 1 on a truncated
  file unless `--json` is given.
- credentials: a keychain that cannot be read at start never leads to a new
  key; the daemon refuses to start with `CREDENTIAL_LOCKED`. A host with no
  keychain backend reads as an empty keychain. The requirement on a missing key
  says a running daemon always holds one, which is what vault-sync's
  no-master-key case assumes.

## Capabilities

### New Capabilities

### Modified Capabilities

- `agent-registry`
- `agent-registry/claude-code`
- `chat`
- `credentials`
- `daemon`
- `skill-manager`

## Impact

Backend: the agent MCP boot heal, the daemon entry point, Codex model discovery,
`skill_file_cmd.py`, `master_key.py`, `keyring_adapter.py` and
`credential_composition.py`. The docs-site agents, skills and credentials guides
change to match. There are no wire-contract or schema changes.
