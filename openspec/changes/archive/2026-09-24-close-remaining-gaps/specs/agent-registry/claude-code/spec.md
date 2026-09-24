## RENAMED Requirements

- FROM: `### Requirement: Install Coffer's MCP entry into ~/.claude.json`
- TO: `### Requirement: Install Coffer's MCP entry into Claude Code's .claude.json`

## MODIFIED Requirements

### Requirement: Locate Claude Code at ~/.claude
The `claude_code` type's standard config directory MUST be `~/.claude/`, which is the value `config_dir` defaults to under [agent-registry](../spec.md) "Validate agent configuration against the agent schema". The presence of that directory MUST be the install marker [agent-registry](../spec.md) "Discover installed agents as candidates without registering them"'s discovery scans for, and [agent-registry](../spec.md) "Allow one agent per name and per config directory"'s one-agent-per-config-directory rule follows from it: Claude Code is registrable once unless the user overrides the path. An overridden `config_dir` is the directory Claude Code is run against through its `CLAUDE_CONFIG_DIR` environment variable — the only way Claude Code reads a config directory other than `~/.claude` — and that is why "Allowlist exactly the files Claude Code reads" places `.claude.json` differently for it. Every Claude Code process Coffer itself starts for such an agent — a chat or channel turn, per [chat](../../chat/spec.md) "Ship Claude Code and Codex subprocess providers" — MUST carry `CLAUDE_CONFIG_DIR=<config_dir>`, so the turn reads the skills, MCP entry and settings Coffer put in that directory; for the default `~/.claude` the variable is left unset.

#### Scenario: discover Claude Code by its config directory
- **GIVEN** a home directory containing `~/.claude/` and no agent registered
- **WHEN** the user runs discovery
- **THEN** a `claude_code` candidate is reported whose `config_dir` is `~/.claude`
- **AND** a `claude_code` agent registered without a `config_dir` resolves to `~/.claude`

### Requirement: Allowlist exactly the files Claude Code reads
The curated allowlist ([agent-registry](../spec.md) "Define a curated config-file allowlist per type") for `claude_code` MUST be exactly: `settings.json`, `settings.local.json`, `.claude.json` under the key `global`, `CLAUDE.md` under the key `instructions`, and the `agents/` directory entry of "Expose personal subagents as a directory entry". `CLAUDE.md` is human-authored instructions and its key says so; the agent's own written memory is the scan of "Scan Claude Code's per-project memory stores" and memory's domain, not this file.

The `global` file MUST be the one Claude Code itself reads for the agent's config directory: `~/.claude.json`, beside the directory, when `config_dir` is the default `~/.claude`; `<config_dir>/.claude.json`, inside it, for any other `config_dir`. Claude Code run with `CLAUDE_CONFIG_DIR` set keeps `.claude.json` inside that directory and never reads `~/.claude.json` — observed on Claude Code 2.1.281, where `claude mcp add -s user` under `CLAUDE_CONFIG_DIR=<dir>` wrote `<dir>/.claude.json` and `claude mcp get` did not see a server kept in `$HOME/.claude.json`. Every reader of that file resolves it this one way, with no fallback to the other location: the config-file editor, the MCP install of "Install Coffer's MCP entry into Claude Code's .claude.json", the entry listing of "Read MCP entries from both Claude Code config files" and the model source of "Read additionalModelOptionsCache without writing it".

#### Scenario: list an agent's config files
- **GIVEN** a registered `claude_code` agent
- **WHEN** the user lists its config files
- **THEN** Coffer returns the curated set for the type — `settings.json`, `settings.local.json`, `.claude.json` (key `global`), `CLAUDE.md` (key `instructions`), and the `agents/` directory entry — each with its resolved path, its containing-folder absolute path (`folder_path`), format, and an `exists` flag (with size + modified time when present)

#### Scenario: resolve .claude.json inside a custom config directory
- **GIVEN** a `claude_code` agent registered with a `config_dir` other than `~/.claude`, and a `.claude.json` both inside that directory and at `~/.claude.json`
- **WHEN** the user lists its config files, lists its MCP entries, and installs Coffer's MCP
- **THEN** the `global` entry's path is `<config_dir>/.claude.json`, the listed `global` MCP entries are the ones in that file, and the `coffer` entry is written into that file
- **AND** `~/.claude.json` is byte-identical before and after

### Requirement: Install Coffer's MCP entry into Claude Code's .claude.json
The `McpInjectionSpec` [agent-registry](../spec.md) "Install Coffer's MCP server into an agent in one action" installs through MUST write `mcpServers.coffer` in the agent's `global` file — `~/.claude.json` for the default config directory, `<config_dir>/.claude.json` for a custom one, per "Allowlist exactly the files Claude Code reads" — a command-map entry whose `command` is the resolved absolute shim path and whose `args` carry `--agent-uid <uid>`. Because the whole JSON document is reserialized on write, the `.bak` of [agent-registry](../spec.md) "Write config files atomically with a backup and an audit entry" is what makes that diff recoverable.

#### Scenario: install Coffer's MCP into an agent
- **GIVEN** a registered `claude_code` agent and a resolvable `coffer-mcp-shim` binary
- **WHEN** the user installs Coffer's MCP
- **THEN** a `coffer` entry is written into `~/.claude.json` `mcpServers` with `command` set to the absolute shim path, the prior file is backed up to `.bak`, an `agent_mcp_installed` audit entry is recorded, and install status reports `installed=true`

### Requirement: Read MCP entries from both Claude Code config files
The entries [agent-registry](../spec.md) "List the MCP entries in the agent's own config files" lists MUST be parsed from BOTH the `global` file's `mcpServers` (`.claude.json`, located per "Allowlist exactly the files Claude Code reads") and `settings.json` `mcpServers`, each entry labelled with the file it came from — verified on a real machine, user-scope MCP servers live in the first and may also appear in the second. The format carries no per-entry enabled flag, so `enabled` is not reported for this type and there is nothing for Coffer to toggle.

#### Scenario: list MCP entries from both Claude Code config files
- **GIVEN** a registered `claude_code` agent with one MCP entry in `~/.claude.json` and another in `settings.json`
- **WHEN** the user lists the agent's MCP entries
- **THEN** both entries are returned, each labelled with the file it came from
- **AND** neither entry reports an `enabled` flag

### Requirement: Read additionalModelOptionsCache without writing it
The native-config source of [agent-registry](../spec.md) "Contribute models from the type's native config read-only" for this type MUST be `additionalModelOptionsCache` in the agent's `.claude.json` — `~/.claude.json` for the default config directory, `<config_dir>/.claude.json` for a custom one, the single location "Allowlist exactly the files Claude Code reads" resolves, with no fallback to the other — which contributes the account's own extra options. It MUST be read only. It is Claude Code's own CACHE of a field from its API response, so anything Coffer wrote into it would be clobbered, and stale entries in it are read as they are; for this type the Coffer-side surfaces stay the only places a model is chosen, because Claude Code has no catalogue file Coffer may own.

#### Scenario: read the account's extra model options from ~/.claude.json
- **GIVEN** a `~/.claude.json` whose `additionalModelOptionsCache` lists an extra model option
- **WHEN** the native-config source is read
- **THEN** that option is returned as a catalogue entry
- **AND** `~/.claude.json` is byte-identical before and after

#### Scenario: read the extra model options from a custom config directory's .claude.json
- **GIVEN** a custom Claude Code config directory whose `.claude.json` lists extra model options, and a `~/.claude.json` listing different ones
- **WHEN** the native-config source is read for that directory
- **THEN** the options returned are the ones in `<config_dir>/.claude.json`
- **AND** none of `~/.claude.json`'s options are returned

### Requirement: Delegate Claude Code plugin uninstall to its CLI
The uninstall strategy of [agent-registry](../spec.md) "Uninstall a plugin by the type's own strategy" for this type MUST be delegation: Coffer runs `claude plugin uninstall <id>` and never hand-writes Claude's internal inventory, because the CLI owns that state. The CLI MUST run against the agent's own config directory: for an agent whose config directory is not the default `~/.claude`, it is started with `CLAUDE_CONFIG_DIR` set to that directory. When the `claude` CLI is not on `PATH` the listing reports `can_uninstall=false` and the operation is `PLUGIN_UNINSTALL_UNSUPPORTED` (422); a CLI that runs and fails surfaces as `PLUGIN_UNINSTALL_FAILED` (422).

#### Scenario: uninstall a Claude Code plugin via its CLI
- **GIVEN** a registered `claude_code` agent with an installed plugin and the `claude` CLI on PATH
- **WHEN** the user uninstalls it
- **THEN** Coffer runs `claude plugin uninstall <id>` (it never hand-writes Claude's internal `installed_plugins.json` / `settings.json`), the request succeeds, and an `agent_plugin_uninstalled` audit entry is recorded

#### Scenario: reject Claude uninstall when its CLI is unavailable
- **GIVEN** a registered `claude_code` agent whose `claude` CLI is not on PATH
- **WHEN** the user attempts to uninstall a plugin
- **THEN** the request is rejected with `unprocessable_entity` (422) and error code `PLUGIN_UNINSTALL_UNSUPPORTED`, and nothing is written — the listing also hides the in-app uninstall affordance in this case

#### Scenario: uninstall runs against a custom config directory
- **GIVEN** a registered `claude_code` agent whose config directory is not `~/.claude`, with an installed plugin
- **WHEN** the user uninstalls the plugin
- **THEN** `claude plugin uninstall <id>` is started with `CLAUDE_CONFIG_DIR` set to that agent's config directory
