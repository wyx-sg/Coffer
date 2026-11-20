# Agent Registry — Antigravity

## Purpose
This child of [`agent-registry`](../spec.md) says how the `antigravity` agent type realises the facets its parent requires of every type, and which ones it lacks: where its config directory is, which of its files Coffer may read and write, the shape of the MCP entry Coffer installs, where skills go, and how the type is detected. It is the prose reading of that type's one `AGENT_DESCRIPTORS` record — default config dir `~/.gemini/config/`, program `agy`, app bundle `Antigravity.app`, its allowlist and its injection spec. Everything the supported types share lives in the parent and is not restated here.

"Antigravity" is Google's product: the Antigravity App, the `agy` CLI and the Antigravity IDE together, because all three read one personal config layer, `~/.gemini/config/`. Each surface keeps its conversations and sign-ins in its own data folder beside it (`~/.gemini/antigravity/`, `~/.gemini/antigravity-cli/`, `~/.gemini/antigravity-ide/`), which Coffer never reads. Why the type joins at the config layer only is [Antigravity Joins Coffer Through Its Config Layer Only](../../../../docs/decisions/antigravity-joins-at-its-config-layer-only.md).

## Requirements

### Requirement: Locate Antigravity at ~/.gemini/config
The `antigravity` type's standard config directory MUST be `~/.gemini/config/`, the personal config layer the Antigravity App, the `agy` CLI and the Antigravity IDE all read. That directory and the product's program are the two signals of [agent-registry](../spec.md) "Detect an agent by its program and its config directory": the program is `agy` on the agent's `PATH`, and, when `agy` is not there, the `Antigravity.app` bundle in the system or the user's Applications folder, whose version is the `CFBundleShortVersionString` of its `Info.plist`. `~/.gemini` alone is never a signal, because the retired Gemini CLI kept its files there too. Antigravity reads no environment variable that moves this directory, so no process Coffer starts carries one.

#### Scenario: discover Antigravity by its shared config folder
- **GIVEN** a home directory containing `~/.gemini/config/`, `agy` on the agent's `PATH`, and no agent registered
- **WHEN** the user runs discovery
- **THEN** an `antigravity` candidate is reported in state `installed_active` whose `config_dir` is `~/.gemini/config`
- **AND** an `antigravity` agent registered without a `config_dir` resolves to `~/.gemini/config`

#### Scenario: detect the Antigravity App without agy
- **GIVEN** `Antigravity.app` in the Applications folder declaring version `2.32.2`, and no `agy` on the agent's `PATH`
- **WHEN** the agent's program is probed
- **THEN** it is found at the app bundle with version `2.32.2`
- **AND** when `agy` is on the `PATH` too, `agy` and its own version win

### Requirement: Allowlist exactly Antigravity's shared config files
The curated allowlist ([agent-registry](../spec.md) "Define a curated config-file allowlist per type") for `antigravity` MUST be exactly: `mcp_config.json` under the key `mcp`, `config.json` under the key `config`, `AGENTS.md` under the key `instructions`, the `rules/` directory under the key `rules`, and `hooks.json` — all inside `~/.gemini/config/`. Nothing under the per-surface data folders `~/.gemini/antigravity/`, `~/.gemini/antigravity-cli/` or `~/.gemini/antigravity-ide/` may enter it: they hold conversations and the MCP OAuth tokens (`mcp_oauth_tokens.json`).

#### Scenario: list exactly Antigravity's five shared config entries
- **GIVEN** a registered `antigravity` agent, and an `~/.gemini/antigravity/` folder holding `mcp_oauth_tokens.json`
- **WHEN** the user lists its config files
- **THEN** exactly five entries are returned — `mcp`, `config`, `instructions`, `rules` (a directory) and `hooks` — each inside `~/.gemini/config/`
- **AND** none of them is under `~/.gemini/antigravity/`

### Requirement: Install Coffer's MCP entry into mcp_config.json
The `McpInjectionSpec` [agent-registry](../spec.md) "Install Coffer's MCP server into an agent in one action" installs through MUST write `mcpServers.coffer` in `mcp_config.json`, whose `command` is the resolved absolute shim path, whose `args` are `["--agent-uid", "<uid>"]` — the command-map shape Claude Code's entry uses — and whose `timeoutSeconds` is `86400`, because Antigravity ends a tool call after 180 seconds and a Coffer tool can wait on the person. An empty file, which the App creates, reads as an empty object. Coffer MUST NOT write an Antigravity permission rule: allowing `coffer` in Antigravity's Ask prompt is the person's choice. Skills are delivered into `~/.gemini/config/skills/`, the folder the three surfaces read personal skills from.

#### Scenario: install Coffer's MCP into an empty mcp_config.json
- **GIVEN** a registered `antigravity` agent whose `mcp_config.json` exists and is empty
- **WHEN** the user connects it to Coffer
- **THEN** `mcpServers.coffer` is written with `command` set to the absolute shim path, `args` set to `--agent-uid` and the agent's uid, and `timeoutSeconds` set to `86400`
- **AND** `~/.gemini/config/skills/` exists for skill delivery

### Requirement: Leave Antigravity's models, memory and sessions to Antigravity
The `antigravity` type MUST have no provider projection, no driver, no memory reader and no session source ([Antigravity Joins Coffer Through Its Config Layer Only](../../../../docs/decisions/antigravity-joins-at-its-config-layer-only.md)): Antigravity runs only Google-hosted models and documents no custom endpoint; Google does not permit wrapping `agy` inside a third-party tool on a personal plan; Antigravity keeps no store of learned memories; and its conversation storage is undocumented. So no model connection reaches it, no chat, channel or scheduled-task picker lists it, memory sync neither reads nor writes it, its native-memory scan, plugin list and hook list are empty, and listing its sessions answers `AGENT_TYPE_UNSUPPORTED`. Coffer MUST read nothing under its per-surface data folders.

#### Scenario: read nothing from Antigravity's per-surface data folders
- **GIVEN** a registered `antigravity` agent and a conversation folder under `~/.gemini/antigravity/brain/`
- **WHEN** the user lists the agent's sessions, native memory, plugins and hooks
- **THEN** the sessions request answers `AGENT_TYPE_UNSUPPORTED`
- **AND** the native memory, plugins and hooks lists are empty
