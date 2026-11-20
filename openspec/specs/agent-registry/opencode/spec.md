# Agent Registry — OpenCode

## Purpose
This child of [`agent-registry`](../spec.md) says how the `opencode` agent type realises the facets its parent defines: where its config directory is, which of its files Coffer may read and write, the shape of the MCP entry Coffer installs, and where its skills are delivered. It is the prose reading of that type's one `AGENT_DESCRIPTORS` record. OpenCode ships a 1.x line and a 2.x line that read the same `~/.config/opencode/opencode.json`; this type serves both (ADR [OpenCode Gets Its MCP Entry in the 1.x Shape](../../../../docs/decisions/opencode-gets-its-mcp-entry-in-the-1x-shape.md)).

OpenCode keeps no memory of its own, so this type has no memory reader.

## Requirements

### Requirement: Locate OpenCode at ~/.config/opencode
The `opencode` type's standard config directory MUST be `~/.config/opencode/`. That directory and the `opencode` program on the agent's `PATH` MUST be the two signals of [agent-registry](../spec.md) "Detect an agent by its program and its config directory"; the version is what `opencode --version` prints. An overridden `config_dir` is the directory OpenCode is run against through `OPENCODE_CONFIG_DIR`.

#### Scenario: discover OpenCode by its config directory
- **GIVEN** a home directory containing `~/.config/opencode/`, the `opencode` program on the agent's `PATH`, and no agent registered
- **WHEN** the user runs discovery
- **THEN** an `opencode` candidate is reported whose `config_dir` is `~/.config/opencode`

### Requirement: Allowlist exactly OpenCode's config and instructions files
The curated allowlist for `opencode` MUST be exactly: `opencode.json` under the key `config` (format `json`; `opencode.jsonc` when that is the only one present), and `AGENTS.md` under the key `instructions`. A config file holding comments does not parse as JSON and is reported in the parent's parse-error state rather than rewritten without them.

#### Scenario: list exactly OpenCode's two config files
- **GIVEN** a registered `opencode` agent
- **WHEN** the user lists its config files
- **THEN** exactly `opencode.json` (format `json`) and `AGENTS.md` under the key `instructions` are returned

### Requirement: Install Coffer's MCP entry into opencode.json as a local command
The `McpInjectionSpec` for this type MUST write `mcp.coffer` in `opencode.json` as `{"type": "local", "command": ["<shim>", "--agent-uid", "<uid>"]}`: the 1.x shape, which the 2.x line also loads. The entries listed for this type MUST be read both from directly under `mcp` and from the 2.x `mcp.servers` map, and removing one MUST remove it from whichever of the two holds it.

#### Scenario: install Coffer's MCP into OpenCode's config
- **GIVEN** a registered `opencode` agent whose `opencode.json` sets a model
- **WHEN** the user installs Coffer's MCP
- **THEN** `mcp.coffer` is a `local` entry whose command array is the shim path, `--agent-uid` and the agent's uid
- **AND** the model setting is kept

#### Scenario: list OpenCode servers of both config lines
- **GIVEN** a registered `opencode` agent whose `opencode.json` has one server directly under `mcp` and one under `mcp.servers`
- **WHEN** the user lists the agent's MCP entries
- **THEN** both servers are listed

### Requirement: Deliver OpenCode's skills to the shared ~/.agents/skills
Skills MUST be delivered to `~/.agents/skills`, which OpenCode reads, as one link shared with every other agent reading that directory. Skills a person keeps in `~/.config/opencode/skills` are listed as unmanaged.

#### Scenario: deliver a skill for OpenCode into ~/.agents/skills
- **GIVEN** a registered `opencode` agent and an enabled skill in scope for it
- **WHEN** skills are reconciled
- **THEN** `~/.agents/skills/<skill>` links to the skill's master folder
