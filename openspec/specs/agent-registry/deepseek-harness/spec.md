# Agent Registry — DeepSeek Harness

## Purpose
This child of [`agent-registry`](../spec.md) says how the `deepseek_harness` agent type realises the facets its parent defines. DeepSeek Harness (`dsh`) is DeepSeek's open-source agent runtime: a local web UI, a headless mode and an ACP mode, all composed from YAML patch layers under `$DSH_HOME` (default `~/.dsh`). It is the prose reading of that type's one `AGENT_DESCRIPTORS` record.

DeepSeek Harness keeps no memory of its own, so this type has no memory reader.

## Requirements

### Requirement: Locate DeepSeek Harness at ~/.dsh
The `deepseek_harness` type's standard config directory MUST be `~/.dsh/`. That directory and the `dsh` program on the agent's `PATH` MUST be the two signals of [agent-registry](../spec.md) "Detect an agent by its program and its config directory". An overridden `config_dir` is the directory DeepSeek Harness is run against through `DSH_HOME`.

#### Scenario: discover DeepSeek Harness by its config directory
- **GIVEN** a home directory containing `~/.dsh/`, the `dsh` program on the agent's `PATH`, and no agent registered
- **WHEN** the user runs discovery
- **THEN** a `deepseek_harness` candidate is reported whose `config_dir` is `~/.dsh`

### Requirement: Allowlist exactly DeepSeek Harness's patch and instructions files
The curated allowlist for `deepseek_harness` MUST be exactly: `cordis.patch.yml` under the key `patch` (the home-level layer applied to every profile), `profiles/web/cordis.patch.yml` under the key `web_patch` (the layer the web UI's settings write), both format `yaml`, and `~/.agents/AGENTS.md` under the key `instructions`.

#### Scenario: list exactly DeepSeek Harness's three config files
- **GIVEN** a registered `deepseek_harness` agent
- **WHEN** the user lists its config files
- **THEN** exactly the two patch files (format `yaml`) and `AGENTS.md` under the key `instructions` are returned

### Requirement: Install Coffer's MCP row as a block Coffer owns
The `McpInjectionSpec` for this type MUST write one `insert` patch holding one `@deepseek-ai/dsh-mcp-client` row (`id: coffer-mcp`, `serverName: coffer`, `transport: stdio`, the shim path as `command`, `["--agent-uid", "<uid>"]` as `args`) between two marker comments at the end of `$DSH_HOME/cordis.patch.yml`. Install replaces that block as text and uninstall removes it; no other byte of the file changes (ADR [DeepSeek Harness's MCP Row Lives in a Block Coffer Owns](../../../../docs/decisions/deepseek-harness-mcp-row-lives-in-a-block-coffer-owns.md)). A file whose top level is not a block-style list is refused with the parent's parse-error state.

#### Scenario: install Coffer's MCP into the home patch keeping the person's rows
- **GIVEN** a registered `deepseek_harness` agent whose `cordis.patch.yml` holds a comment, a `!!js` value and an MCP row of the person's
- **WHEN** the user installs Coffer's MCP and then uninstalls it
- **THEN** after the install the file ends with Coffer's marked block and starts with the person's text unchanged
- **AND** after the uninstall the file is the person's text again

### Requirement: List DeepSeek Harness MCP rows without rewriting them
The entries listed for this type MUST be every `@deepseek-ai/dsh-mcp-client` row in both patch files, named by `config.serverName`. Removing or importing one of the person's rows MUST be refused with `MCP_ENTRY_NOT_EDITABLE` (422), because Coffer never re-serialises those files.

#### Scenario: refuse to remove a DeepSeek Harness MCP row
- **GIVEN** a registered `deepseek_harness` agent whose `cordis.patch.yml` holds an MCP row named `memory`
- **WHEN** the user lists the agent's MCP entries and then removes `memory`
- **THEN** `memory` is listed
- **AND** the removal is refused with `MCP_ENTRY_NOT_EDITABLE` and the file is unchanged

### Requirement: Deliver DeepSeek Harness's skills to the shared ~/.agents/skills
Skills MUST be delivered to `~/.agents/skills`, which DeepSeek Harness reads, as one link shared with every other agent reading that directory. Skills a person keeps in `~/.dsh/skills` are listed as unmanaged.

#### Scenario: deliver a skill for DeepSeek Harness into ~/.agents/skills
- **GIVEN** a registered `deepseek_harness` agent and an enabled skill in scope for it
- **WHEN** skills are reconciled
- **THEN** `~/.agents/skills/<skill>` links to the skill's master folder
