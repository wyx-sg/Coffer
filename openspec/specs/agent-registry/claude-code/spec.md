# Agent Registry — Claude Code

## Purpose
This child of [`agent-registry`](../spec.md) says how the `claude_code` agent type realises each facet its parent defines: where its config directory is, which of its files Coffer may read and write, the shape of the MCP entry Coffer installs, where its plugin inventory and enabled state live, how its model catalogue and reasoning levels are read back, where it keeps its own memory, and where it writes its transcripts. It is the prose reading of that type's one `AGENT_DESCRIPTORS` record — default config dir `~/.claude/`, its allowlist, its injection spec, a `PluginCapability` whose uninstall strategy is CLI delegation, its native-memory layout, its transcript location and its catalogue sources. Everything the two supported types share, and everything the parent assumes, lives in the parent and is not restated here.

"Claude Code" is the product: its CLI and its IDE/desktop form together, because they read one shared config directory. The separate **Claude Desktop** chat app has its own config directory and is not this type. Claude Code keeps its plugin inventory in files it owns and its enabled state in a file the user owns; Coffer reads the first, writes only the second, and hands an uninstall to Claude Code's own CLI. `.claude.json` sits beside the default config directory (`~/.claude.json`) and inside a custom one (`<config_dir>/.claude.json`, where Claude Code keeps it when run with `CLAUDE_CONFIG_DIR`); only its `mcpServers` map is a write target, and the rest of that file is the agent's own state, read where needed and never written.

## Requirements

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

### Requirement: Expose personal subagents as a directory entry
`agents/` MUST be the type's directory entry ([agent-registry](../spec.md) "List directory config entries"): one Markdown file per personal subagent, nested paths allowed, each child addressed and validated per [agent-registry](../spec.md) "Read, write and delete files inside a directory entry".

#### Scenario: list nested subagent files in the agents directory
- **GIVEN** a registered `claude_code` agent whose `agents/` directory holds a subagent file at its top level and another in a nested folder
- **WHEN** the user lists the `agents` config entry
- **THEN** the entry reports `kind=directory` and both files by their entry-relative paths, the nested one included

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

### Requirement: Require the source file for a name carried by both files
A name present in both source files MUST be listed twice, once per file. A remove ([agent-registry](../spec.md) "Remove a direct MCP entry from its source file") or adopt ([agent-registry](../spec.md) "Adopt a direct MCP entry into Coffer") request MUST therefore carry the source file; a request that does not, for a name carried by both, is rejected as ambiguous rather than guessing which file to edit.

#### Scenario: reject an ambiguous MCP entry removal without a source
- **GIVEN** a registered `claude_code` agent whose `~/.claude.json` and `settings.json` both carry an MCP entry of the same name
- **WHEN** the user removes that entry without naming its source file
- **THEN** the request is rejected as ambiguous
- **AND** both files are unchanged

### Requirement: Read the plugin inventory from Claude Code's own files
The inventory [agent-registry](../spec.md) "List an agent's installed plugins without writing anything" lists MUST be derived from `<config_dir>/plugins/installed_plugins.json` and `known_marketplaces.json` — read, never written — with each plugin's enabled state read from the `enabledPlugins` map in `settings.json`, and `cache_present` from the install path the inventory records.

#### Scenario: read enabled state from settings.json and cache from the inventory
- **GIVEN** a registered `claude_code` agent whose `installed_plugins.json` records two plugins with install paths, one of them missing on disk, and whose `settings.json` `enabledPlugins` disables one
- **WHEN** the user lists the agent's plugins
- **THEN** each plugin's enabled state is the one `enabledPlugins` declares
- **AND** the plugin whose install path is missing reports `cache_present=false`

### Requirement: Toggle Claude Code plugins in settings.json only
The toggle of [agent-registry](../spec.md) "Toggle a plugin through the documented location only" MUST write only the `enabledPlugins` map in `settings.json`. `installed_plugins.json` and `known_marketplaces.json` MUST be byte-identical before and after, and a plugin listing likewise leaves them byte-identical.

#### Scenario: toggle a Claude Code plugin without touching its inventory
- **GIVEN** a registered `claude_code` agent with an enabled plugin
- **WHEN** the user disables it
- **THEN** `settings.json` `enabledPlugins` records it as disabled
- **AND** `installed_plugins.json` and `known_marketplaces.json` are byte-identical before and after

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

### Requirement: Offer the Claude Code CLI's own model aliases
The first catalogue source of [agent-registry](../spec.md) "Read the model catalogue back from the installed agent" for this type MUST be the CLI's own embedded **alias table**. The ids are the aliases the CLI itself accepts, and each label is the display name of the model that alias resolves to on a first-party account, so a release that moves an alias relabels the picker on its own. Both halves come from one embedded blob, located structurally; an anchor that stops matching MUST cost this source entirely rather than falling back to anything Coffer wrote down. The reason is entitlement: the versioned catalog is cumulative and account-blind, nothing on the machine says which of its models a given account may run, and the CLI's own picker offers the aliases and resolves each against the account at turn time. With the alias table unreachable the catalogue still answers from the remaining sources.

#### Scenario: offer the embedded aliases and nothing when the table is missing
- **GIVEN** a `claude` binary whose embedded bundle carries the alias table
- **WHEN** the alias source is read
- **THEN** each entry's id is an alias the CLI accepts, labelled with the display name of the model it resolves to
- **AND** a binary whose bundle lacks the alias table contributes no entries at all

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

### Requirement: Read effort levels from the installed Claude Agent SDK
The runtime source of [agent-registry](../spec.md) "Read reasoning-effort levels from the agent runtime" for this type MUST be the installed Claude Agent SDK's own `EffortLevel` alias, read once and applied to every catalogue entry — the levels are a property of the runtime, not of a model, and `ClaudeAgentOptions.effort` renders as the CLI's own effort flag. An SDK that declares none — or an environment without the SDK installed alongside the daemon — yields an empty tuple and the controls hide themselves. No default level MAY be reported ([agent-registry](../spec.md) "Report no default effort the runtime does not publish"): `ClaudeAgentOptions.effort` defaults to `None`, meaning "whatever the CLI decides", and the CLI does not say what that is.

#### Scenario: apply the SDK's effort levels to every alias without a default
- **GIVEN** the installed Claude Agent SDK declares its `EffortLevel` levels
- **WHEN** the Claude Code catalogue is read
- **THEN** every entry carries exactly those levels
- **AND** no entry reports a `default_effort`

### Requirement: Scan Claude Code's per-project memory stores
The native-memory layout of [agent-registry](../spec.md) "Scan an agent's own native memory stores read-only" for this type MUST be per project at `<config_dir>/projects/<slug>/memory/` — one row per project that has a `memory/` directory. The `project` label and `path` MUST be the REAL project directory, recovered from that project's session-transcript `cwd`; the slug encoding is lossy (`/`, `.` and `_` all collapse to `-`), so decoding the slug is a last-resort fallback — used, for example, when a project's transcripts are gone but its memory directory remains — and never the preferred source.

#### Scenario: the native memory scan lists an agent's own per-project stores
- **GIVEN** a registered `claude_code` agent whose `<config_dir>/projects/<slug>/memory` directory holds `.md` fact files (plus a `MEMORY.md` index)
- **WHEN** the user scans the agent's native memory
- **THEN** Coffer returns one store per project with a `project` label and `path` that are the REAL project directory (recovered from the project's session-transcript `cwd`, not the lossy slug), the real `memory_dir`, and an `item_count` of `.md` files excluding `MEMORY.md` (or `1` for a store whose only content is an inline `MEMORY.md`) — read-only, deriving everything from disk and emitting no audit event. An agent with no `projects/` directory returns an empty list.

### Requirement: Count memory items excluding the MEMORY.md index
`item_count` for a store MUST be the number of `.md` fact files excluding `MEMORY.md` — or `1` when there are no fact files but `MEMORY.md` itself holds inline content, which is an older or hand-written hub document and is still one item of memory.

#### Scenario: count an inline MEMORY.md as one item
- **GIVEN** a project memory directory whose only file is a `MEMORY.md` with inline content
- **WHEN** the native memory is scanned
- **THEN** that store reports an `item_count` of 1
- **AND** a store holding fact files beside its `MEMORY.md` counts only the fact files

### Requirement: Read Claude Code transcripts from the projects directory
The transcript location of [agent-registry](../spec.md) "List an agent's transcript sessions read-only" for this type MUST be `<config_dir>/projects/**/*.jsonl`. That directory is also the parent of this type's memory stores, which is why the store read of [agent-registry](../spec.md) "Read one native memory store's files read-only" MUST accept only a directory the layout of "Scan Claude Code's per-project memory stores" would have listed and reject a sibling path under `projects/` that merely looks like one.

#### Scenario: list sessions from projects and refuse a sibling as a memory store
- **GIVEN** a registered `claude_code` agent with a session `.jsonl` and a `memory/` store under `<config_dir>/projects/<slug>/`
- **WHEN** the user lists the agent's transcripts and then opens `<config_dir>/projects/<slug>` as a memory store
- **THEN** the session is listed
- **AND** the store read is rejected as `not_found` (404)
