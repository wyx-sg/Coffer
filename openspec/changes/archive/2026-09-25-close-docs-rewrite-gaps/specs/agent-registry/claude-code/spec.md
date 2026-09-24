## MODIFIED Requirements

### Requirement: Allowlist exactly the files Claude Code reads
The curated allowlist ([agent-registry](../spec.md) "Define a curated config-file allowlist per type") for `claude_code` MUST be exactly: `settings.json`, `settings.local.json`, `.claude.json` under the key `global`, `CLAUDE.md` under the key `instructions`, and the `agents/` directory entry of "Expose personal subagents as a directory entry" under the key `subagents`. `CLAUDE.md` is human-authored instructions and its key says so; the agent's own written memory is the scan of "Scan Claude Code's per-project memory stores" and memory's domain, not this file.

The `global` file MUST be the one Claude Code itself reads for the agent's config directory: `~/.claude.json`, beside the directory, when `config_dir` is the default `~/.claude`; `<config_dir>/.claude.json`, inside it, for any other `config_dir`. Claude Code run with `CLAUDE_CONFIG_DIR` set keeps `.claude.json` inside that directory and never reads `~/.claude.json` — observed on Claude Code 2.1.281, where `claude mcp add -s user` under `CLAUDE_CONFIG_DIR=<dir>` wrote `<dir>/.claude.json` and `claude mcp get` did not see a server kept in `$HOME/.claude.json`. Every reader of that file resolves it this one way, with no fallback to the other location: the config-file editor, the MCP install of "Install Coffer's MCP entry into Claude Code's .claude.json", the entry listing of "Read MCP entries from both Claude Code config files" and the model source of "Read additionalModelOptionsCache without writing it".

#### Scenario: list an agent's config files
- **GIVEN** a registered `claude_code` agent
- **WHEN** the user lists its config files
- **THEN** Coffer returns the curated set for the type — `settings.json`, `settings.local.json`, `.claude.json` (key `global`), `CLAUDE.md` (key `instructions`), and the `agents/` directory entry (key `subagents`) — each with its resolved path, its containing-folder absolute path (`folder_path`), format, and an `exists` flag (with size + modified time when present)

#### Scenario: resolve .claude.json inside a custom config directory
- **GIVEN** a `claude_code` agent registered with a `config_dir` other than `~/.claude`, and a `.claude.json` both inside that directory and at `~/.claude.json`
- **WHEN** the user lists its config files, lists its MCP entries, and installs Coffer's MCP
- **THEN** the `global` entry's path is `<config_dir>/.claude.json`, the listed `global` MCP entries are the ones in that file, and the `coffer` entry is written into that file
- **AND** `~/.claude.json` is byte-identical before and after
