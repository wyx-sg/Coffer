## RENAMED Requirements

- FROM: `### Requirement: Support exactly the Claude Code and Codex agent types`
- TO: `### Requirement: Support exactly the Claude Code, Codex and Antigravity agent types`

## MODIFIED Requirements

### Requirement: Support exactly the Claude Code, Codex and Antigravity agent types
The system MUST support the agent types `claude_code`, `codex` and `antigravity`; registering any type outside the manifest (e.g. the `claude_desktop` chat app, the retired Gemini CLI) is rejected with `unprocessable_entity` (422). The rejection carries the generic request-validation message and never echoes the submitted value back. Per-type behaviour is defined by the capability manifest (`AGENT_DESCRIPTORS`) — per-type values in the record, per-type mechanisms in the optional facets it names ([Agent Mechanisms Are Optional Facets on the Descriptor](../../../docs/decisions/agent-mechanisms-are-optional-facets-on-the-descriptor.md)) — so adding a type is one enum value, one descriptor record with the facet implementations it has, and one child spec. Each supported type covers both the CLI and the app/IDE form of that product, which share one config directory.

What a facet looks like for one type is that type's child spec. There is no per-facet capability matrix and no capability booleans on the wire. A type MAY lack a mechanism facet — a provider projection, a driver, a memory reader or a session source — when its product offers no documented, permitted way to provide it; its child spec says which and why, and the surfaces built on that facet leave the type out (no chat or channel picker lists an agent without a driver, no connection reaches an agent without a provider projection). The config-file allowlist, Coffer's MCP entry, skill delivery and the dependency probe are required of every type ([Antigravity Joins Coffer Through Its Config Layer Only](../../../docs/decisions/antigravity-joins-at-its-config-layer-only.md)). The `PluginCapability` flags of "Toggle a plugin through the documented location only" and "Uninstall a plugin by the type's own strategy" are the one exception, and they are per-facet *runtime availability* — whether the agent's own uninstall command is on `PATH` — not a per-type support claim. A further product is added only when it is genuinely in use and its facets can be exercised on a real install; `opencode`, `hermes`, `cursor` and `openclaw` were removed for lacking exactly that.

#### Scenario: reject unsupported agent type
- **GIVEN** the daemon is running
- **WHEN** the user attempts to register an agent of a type outside the supported set (e.g. `claude_desktop`, `gemini_cli`, or a garbage value)
- **THEN** registration is rejected with `unprocessable_entity` (422), and nothing is persisted

### Requirement: Detect an agent by its program and its config directory
The system MUST detect an agent from two signals: its program on the agent's real `PATH` — the user's login-shell `PATH` merged with the daemon's inherited one, asked through the platform layer — together with the version that program reports, and its config directory on disk. A type whose product also ships as a desktop app names its app bundle; when the program is not on the `PATH`, the bundle found where the operating system keeps applications counts as the program, with the version its bundle declares, so an app-only install reads as installed. The version MUST be read with the program's own version flag under a bounded timeout, and detection MUST NOT run anything that needs a login, a network call or the agent's config. The two signals MUST be named as one state: `installed_active` (program and directory), `installed_never_run` (program, no directory yet), `config_only` (directory, program missing) and `missing` (neither). Discovery candidates, the per-type listing of "Report every supported type's detection state" and every registered agent read (`GET /api/v1/agents`, `GET /api/v1/agents/{uid}`) MUST carry the state and the version, read at request time and never stored. An `installed_never_run` agent can be added: its program works and the directory it has not created yet is created by the registration (see "Validate the config directory at registration"). A `config_only` agent is shown as config left behind with its program not found — not as not installed — because a directory of its own is still on disk and the fix is to reinstall the program; `missing` is shown as not installed.

#### Scenario: read the installed program's version
- **GIVEN** the agent's program is on the agent's `PATH` and answers its version flag with `2.1.281 (Claude Code)`
- **WHEN** the agent is detected
- **THEN** the program is found and its version is `2.1.281`
- **AND** a program that does not answer within the bound is still found, with no version

#### Scenario: offer an installed agent that has never run
- **GIVEN** a supported agent's program is on its `PATH` and its standard config directory does not exist
- **WHEN** the user runs discovery
- **THEN** that type is a candidate in state `installed_never_run`, with its version and its standard config directory marked as not created, and is offered for adding

#### Scenario: show a leftover config directory as config left behind
- **GIVEN** a supported agent's standard config directory exists and its program is not on its `PATH`
- **WHEN** the user runs discovery
- **THEN** that type is a candidate in state `config_only`, with no version, shown as config left behind with its program not found, and is not offered for adding

#### Scenario: offer the directory named by the agent's environment variable
- **GIVEN** the daemon's environment sets `CLAUDE_CONFIG_DIR` to an existing directory other than `~/.claude`, `~/.claude` exists, and Claude Code's program is installed
- **WHEN** the user runs discovery
- **THEN** Claude Code is one candidate at `~/.claude` whose `other_config_dir` is the variable's directory
- **AND** when `~/.claude` does not exist the candidate is the variable's directory, and a variable naming the standard directory adds nothing

#### Scenario: report a registered agent's detection state
- **GIVEN** a registered agent whose program is installed and whose config directory exists
- **WHEN** the agent is read
- **THEN** it carries state `installed_active` and the program's version
- **AND** an agent whose program and directory are both gone reads `missing`

### Requirement: List the supported agents as fixed rows on the Agents page
The Agents page MUST list exactly one row per supported agent type — today three, Claude Code, Codex and Antigravity — whether or not each is installed or added, in that order, so the page reads the same on every machine and a first-time user sees at once what Coffer can manage. Each row is found automatically from the detection state of "Detect an agent by its program and its config directory": an `installed_active` type's row reads as its Coffer state ("Show the Coffer connection on the agent pages") with its config directory and version; an `installed_never_run` type reads Not connected too, with its config directory marked as not created, and offers Connect, whose review names the directory it creates and the only entries Coffer needs in it; a `config_only` type reads as config left behind — program not found — and a `missing` type as not installed, each with no Connect and the daemon's prompt that hands reinstalling or installing it to an agent (see "Hand installing an agent's program to an agent") as the split button **Ask an agent ▾** beside its ⋯ menu — Copy prompt behind the chevron, and Copy prompt alone while no other agent can run it. A row whose program is missing shows no version, and its second line says "Not on this Mac" or what is left in the directory. The page MUST NOT show an install command, and carries no Remove action. On first run, with no agent connected and at least two connectable, the page MUST offer **Connect all**, which reviews and connects every connectable agent in one confirmation. An agent is named by its type everywhere in the web UI; the page offers no field to name one.

Overview's Needs you lists only agents that need the person: an agent that needs repair and one whose config directory is left behind. Not installed, Not connected and a first run raise none.

#### Scenario: the agents page shows both supported agents on first run
- **GIVEN** a fresh Coffer with Claude Code and Codex both installed, Antigravity not installed, and none connected
- **WHEN** the user opens the Agents page
- **THEN** it shows Claude Code then Codex, each reading Not connected with a Connect action, then Antigravity as not installed, and a Connect all action, and Overview lists none as needing the person
- **AND** choosing Connect all reviews the writes for the two connectable agents and, on apply, registers and connects both

#### Scenario: an agent that is not installed shows how to install it
- **GIVEN** Codex not installed on the machine
- **WHEN** the Agents page renders
- **THEN** the Codex row reads as not installed and offers the hand-off split button carrying the daemon's prompt that hands installing Codex to an agent, shows no install command, and has no Connect action
- **AND** its ⋯ menu offers neither Copy prompt nor Ask an agent

#### Scenario: an installed agent that has never run can be added
- **GIVEN** Codex's program installed and `~/.codex` not created
- **WHEN** the Agents page renders and the user chooses Connect on the Codex row
- **THEN** the row reads Not connected, with `~/.codex` marked not created
- **AND** the review names `~/.codex` as created and lists only the entries Coffer adds, and nothing is written until the user applies it

#### Scenario: a leftover config directory reads as config left behind
- **GIVEN** `~/.codex` present and the Codex program not on the agent's `PATH`
- **WHEN** the Agents page renders
- **THEN** the Codex row reads as config left behind — program not found — offering the hand-off split button with the daemon's reinstall prompt, no install command, and no Connect action
- **AND** Overview's Needs you lists it

#### Scenario: a row's menu offers a different config directory
- **GIVEN** a Claude Code row on the Agents page
- **WHEN** the user opens the row's menu
- **THEN** it offers Use a different config directory…, and the page carries no Add agent dialog, no Remove action and no name field
