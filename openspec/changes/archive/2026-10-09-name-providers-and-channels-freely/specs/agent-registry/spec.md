## MODIFIED Requirements

### Requirement: Manage the agent lifecycle
Users MUST be able to register, list, view, update (its config directory and the model binding of "Carry the model binding on the agent record") and remove agents. An agent cannot be switched off: its kind is non-toggleable, so the generic `POST /api/v1/resources/{uid}/enable|disable` routes refuse it with `RESOURCE_NOT_TOGGLEABLE` and its resource always reads enabled. Registration takes the type and, optionally, a config directory — the type's standard one when omitted — and the name is the type's ("Keep one agent per type, named by it"); there is no name or description to supply or edit. Skill bindings between an agent and a skill belong to skill-manager; this registry defines no skill operations beyond exposing an `on_delete` hook for cascade cleanup.

Over REST the lifecycle is `POST /api/v1/agents` (the type and, optionally, `config_dir`), `GET /api/v1/agents` and `GET /api/v1/agents/{uid}`, `PATCH /api/v1/agents/{uid}` (with `config_dir` and the model fields of "Carry the model binding on the agent record") and `DELETE /api/v1/agents/{uid}`, where `{uid}` is the agent's uid or the type it is named by ("Keep one agent per type, named by it"); the Agents page reaches the same operations through each row's Connect and ⋯ menu. The `agent` kind has no scope, because it declares none. The agent's Coffer connection, part by part ("Report an agent's Coffer connection part by part"), is read from `GET /api/v1/agents/{uid}/coffer-connection`: its state and, for each applicable part (the gateway MCP entry, and the memory delivery hook while memory is on), whether it is installed.

#### Scenario: register an agent without an explicit name
- **GIVEN** the daemon is running and no `claude_code` agent is registered
- **WHEN** the user registers an agent with `POST /api/v1/agents`, supplying only the type `claude_code`
- **THEN** the agent is registered under the type's name `claude-code` (underscores become hyphens) at the type's standard config directory, audited as `resource_created`

#### Scenario: update an existing agent
- **GIVEN** a registered agent
- **WHEN** the user updates its `config_dir` to a new writable path
- **THEN** the change persists, an audit entry is recorded, and subsequent operations see the new path

#### Scenario: remove an agent
- **GIVEN** a registered agent (any binding cleanup is handled by the skill-manager spec)
- **WHEN** the user removes it
- **THEN** the agent is deleted, an audit entry is recorded, and `GET /api/v1/agents` no longer lists it

#### Scenario: move an agent to a different config directory
- **GIVEN** a registered agent `claude-code` at `~/.claude` and another writable directory
- **WHEN** the user sends `PATCH /api/v1/agents/claude-code` with `config_dir` set to `<dir>`
- **THEN** `GET /api/v1/agents/claude-code` reports `<dir>` as its config directory, with the same uid and name
- **AND** the update route offers no way to change the name or description

### Requirement: Keep one agent per type, named by it
A machine MUST hold at most one agent of each supported type, and that agent's `name` MUST be its type's name — `claude-code` for `claude_code`, `codex` for `codex` — derived from the type at registration, never chosen by a person. The name is fixed: a changed name MUST be refused with `NAME_IMMUTABLE` (409) whose message says the name is the agent's type. An agent MUST carry no `title` and no `description`: neither registration nor update takes a description, and no surface shows a title for one. Its config directory is the one per-agent setting besides the type and the model binding of "Carry the model binding on the agent record". Registering a type that already has an agent MUST be refused with `AGENT_TYPE_REGISTERED` (409) and nothing persisted; using a different directory is an edit of the one agent.

Because a type names exactly one agent, every `/api/v1/agents/{uid}/…` route MUST also accept the type — its name (`claude-code`) or its value (`claude_code`) — in place of the uid, and answer exactly as it does for the uid; a type with no agent registered reads as not found.

#### Scenario: register a second agent of a registered type
- **GIVEN** a `codex` agent is registered at `~/.codex`
- **WHEN** the user registers another `codex` agent, on `~/.codex` or on any other writable directory
- **THEN** the registration is refused with `AGENT_TYPE_REGISTERED` (409) and nothing is persisted or created on disk
- **AND** the registered agent is still named `codex` and keeps its uid

#### Scenario: address an agent by its type
- **GIVEN** a registered `claude_code` agent with uid `U`
- **WHEN** the user requests `/api/v1/agents/claude-code`, `/api/v1/agents/claude_code/config-files` and `/api/v1/agents/U`
- **THEN** each answers for the same agent, with name `claude-code` and uid `U`
- **AND** `/api/v1/agents/codex` answers not found while no `codex` agent is registered

#### Scenario: an agent's name and description cannot be set
- **GIVEN** a registered `claude-code` agent
- **WHEN** the user submits a new name through the kind-agnostic update route
- **THEN** the name is refused with `NAME_IMMUTABLE` (409) saying the name is the agent's type
- **AND** registering an agent under any name other than its type's is refused as a validation error

### Requirement: List the supported agents as fixed rows on the Agents page
The Agents page MUST list exactly one row per supported agent type — today two, Claude Code and Codex — whether or not each is installed or added, in that order, so the page reads the same on every machine and a first-time user sees at once what Coffer can manage. Each row is found automatically from the detection state of "Detect an agent by its program and its config directory": an `installed_active` type's row reads as its Coffer state ("Show the Coffer connection on the agent pages") with its config directory and version; an `installed_never_run` type reads Not connected too, with its config directory marked as not created, and offers Connect, whose review names the directory it creates and the only entries Coffer needs in it; a `config_only` type reads as config left behind — program not found — and a `missing` type as not installed, each with no Connect and the daemon's prompt that hands reinstalling or installing it to an agent (see "Hand installing an agent's program to an agent") as the split button **Ask an agent ▾** beside its ⋯ menu — Copy prompt behind the chevron, and Copy prompt alone while no other agent can run it. A row whose program is missing shows no version, and its second line says "Not on this Mac" or what is left in the directory. The page MUST NOT show an install command, and carries no Remove action. On first run, with neither agent connected and both connectable, the page MUST offer **Connect both**, which reviews and connects every connectable agent in one confirmation. An agent is named by its type everywhere in the web UI; the page offers no field to name one.

Overview's Needs you lists only agents that need the person: an agent that needs repair, one whose config directory is left behind, one whose Coffer memory hook the agent will not run (reported once, by the reconciler's memory-hook target), and one whose hook it runs but has never fired ("Report an agent whose Coffer hook never fires"). Not installed, Not connected and a first run raise none.

#### Scenario: the agents page shows both supported agents on first run
- **GIVEN** a fresh Coffer with Claude Code and Codex both installed and neither connected
- **WHEN** the user opens the Agents page
- **THEN** it shows exactly two rows, Claude Code then Codex, each reading Not connected with a Connect action, and a Connect both action, and Overview lists neither as needing the person
- **AND** choosing Connect both reviews the writes for both agents and, on apply, registers and connects both

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
