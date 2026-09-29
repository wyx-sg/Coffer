## ADDED Requirements

### Requirement: Keep one agent per type, named by it
A machine MUST hold at most one agent of each supported type, and that agent's `name` MUST be its type's name — `claude-code` for `claude_code`, `codex` for `codex` — derived from the type at registration, never chosen by a person. The name is fixed: a changed name MUST be refused with `NAME_IMMUTABLE` (409) whose message says the name is the agent's type. An agent MUST carry no `title` and no `description`: a non-empty title is refused as a validation error (422) on every surface, and neither registration nor update takes a description. Its config directory is the one per-agent setting besides the type and the model binding of "Carry the model binding on the agent record". Registering a type that already has an agent MUST be refused with `AGENT_TYPE_REGISTERED` (409) and nothing persisted; using a different directory is an edit of the one agent.

Because a type names exactly one agent, every `/api/v1/agents/{uid}/…` route MUST also accept the type — its name (`claude-code`) or its value (`claude_code`) — in place of the uid, and answer exactly as it does for the uid; a type with no agent registered reads as not found. Every `coffer agent` command, `coffer path agent`, `coffer scan --agent` and a reach's `--agents` MUST take the type the same way, or a uid.

A database holding several agents of one type from before this rule MUST be collapsed on upgrade to one: the one whose own Coffer MCP entry names its uid, else an enabled one, else the most recently used, else the one on the type's standard directory, else the oldest. Every reach list and channel `default_agent` that named a dropped agent MUST be re-pointed at the kept one — a reach list never widened to every agent by it — the kept agent renamed to its type with its title and description cleared, and each dropped agent reported in the daemon log with its type, name, uid, config directory and the uid kept in its place. Nothing is written into a dropped agent's config directory.

#### Scenario: register a second agent of a registered type
- **GIVEN** a `codex` agent is registered at `~/.codex`
- **WHEN** the user registers another `codex` agent, on `~/.codex` or on any other writable directory
- **THEN** the registration is refused with `AGENT_TYPE_REGISTERED` (409) and nothing is persisted or created on disk
- **AND** the registered agent is still named `codex` and keeps its uid

#### Scenario: address an agent by its type
- **GIVEN** a registered `claude_code` agent with uid `U`
- **WHEN** the user requests `/api/v1/agents/claude-code`, `/api/v1/agents/claude_code/config-files` and `/api/v1/agents/U`, and runs `coffer agent show claude-code`
- **THEN** each answers for the same agent, with name `claude-code` and uid `U`
- **AND** `/api/v1/agents/codex` answers not found while no `codex` agent is registered

#### Scenario: an agent's name, title and description cannot be set
- **GIVEN** a registered `claude-code` agent
- **WHEN** the user submits a new name, then a title, through the kind-agnostic update route
- **THEN** the name is refused with `NAME_IMMUTABLE` (409) saying the name is the agent's type, and the title is refused as a validation error (422)
- **AND** registering an agent under any name other than its type's is refused as a validation error

#### Scenario: collapse duplicate agents to one per type on upgrade
- **GIVEN** a database from before this rule with two `claude_code` agents — one enabled, one disabled but touched more recently — a skill whose reach names both, an MCP server whose reach names only the disabled one, and a channel whose default agent is the disabled one
- **WHEN** the database is upgraded
- **THEN** only the enabled agent remains, named `claude-code` with no title or description, and the skill's reach names it once, the MCP server's reach names it, and the channel's default agent is it
- **AND** the daemon log reports the dropped agent's name, uid and config directory beside the uid kept in its place

### Requirement: Report every supported type's detection state
The system MUST serve `GET /api/v1/agents/types`, one row per supported type in manifest order whether or not an agent of it is registered, so a surface can always render one row per type. Each row MUST carry the `type`, its agent's `name`, the `display_name`, the `config_dir` — the registered agent's, or the one registering would use — the type's `standard_config_dir`, the `default_skill_dir`, the detection `state` and `version` of "Detect an agent by its program and its config directory", the registered agent's `uid` (`null` when none), whether it is `addable` now, and `other_config_dir`: an existing directory the type's own environment variable (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`) names in the daemon's environment other than `config_dir`, offered as a different config directory to use, never as a second agent. A type not registered is `addable` exactly when its program is installed. The read is derived at request time, stores nothing and audits nothing.

#### Scenario: list every supported type whether added or not
- **GIVEN** a registered `claude_code` agent, and Codex installed but never run — its program on its `PATH` and `~/.codex` absent
- **WHEN** the user requests `GET /api/v1/agents/types`
- **THEN** the response has exactly two rows: `claude_code` with the agent's uid, its directory and `addable` false, and `codex` with no uid, state `installed_never_run`, `config_dir` `~/.codex` and `addable` true
- **AND** nothing is registered or created by the read

### Requirement: Serve each agent type's model catalogue from its one agent
`GET /api/v1/agent-providers/{agent_key}/models` MUST answer, per agent type, which models a picker offers for that agent: the agent's own catalogue, read back from the installed agent and never written down in Coffer, unless an active connection for that agent curates a set of ids — then those ids, as [provider-switching](../provider-switching/spec.md) "Serve one model list to every surface" defines. Each entry MUST carry `id` (passed to the agent verbatim), `label`, `description`, the reasoning `efforts` its runtime reports and the `default_effort` it would use, keeping a reported default only when it is one of the offered levels. An unknown `agent_key` MUST be a 404. The catalogue reads the native config of the type's one agent ("Keep one agent per type, named by it") while it is enabled, which is also the agent a chat turn on that type runs against ([chat](../chat/spec.md) "Ship Claude Code and Codex subprocess providers").

#### Scenario: list the models an agent can be put on
- **GIVEN** a registered `codex` agent whose own config names a model
- **WHEN** the user requests `GET /api/v1/agent-providers/codex/models`
- **THEN** the response lists that model with `id`, `label`, `description`, `efforts` and `default_effort`
- **AND** the same request for an unknown agent key answers 404


## MODIFIED Requirements

### Requirement: Register each agent as an agent resource identified by its uid
The system MUST register each known local agent as a Resource of kind `agent`, identified by the immutable `uid` the resource framework mints for it ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)). Its name is its type's ("Keep one agent per type, named by it"), and every reference another kind holds to an agent — a resource `scope`'s agent list, a channel's `default_agent`, the `--agent-uid` the shim reports — holds the uid, so the reference survives the agent being removed and registered again only if it is re-pointed, never by coincidence of a name.

#### Scenario: keep an agent's uid across a rename
- **GIVEN** a registered agent with uid `U` named `codex`
- **WHEN** the user tries to rename it to `after`
- **THEN** the rename is refused with `NAME_IMMUTABLE` and the agent is still read back at `/api/v1/agents/U` with uid `U`, name `codex` and its config dir unchanged
- **AND** `after` addresses nothing as a path segment

#### Scenario: keep an agent's uid while its directory moves
- **GIVEN** a registered agent with uid `U` named `codex`
- **WHEN** the user moves it to another writable config directory
- **THEN** the agent is still read back at `/api/v1/agents/U` and at `/api/v1/agents/codex` with uid `U`, name `codex` and the new config directory

### Requirement: Manage the agent lifecycle
Users MUST be able to register, list, view, update (its config directory and the model binding of "Carry the model binding on the agent record") and remove agents. An agent also carries the kind-agnostic `enabled` flag every Resource has; switching it is "Switch an agent off with the kind-agnostic enabled flag", not a field of the agent's own update. Registration takes the type and, optionally, a config directory — the type's standard one when omitted — and the name is the type's ("Keep one agent per type, named by it"); there is no name, title or description to supply or edit. Skill bindings between an agent and a skill belong to skill-manager; this registry defines no skill operations beyond exposing an `on_delete` hook for cascade cleanup and an `on_enabled_changed` hook for the reclaim of "Switch an agent off with the kind-agnostic enabled flag".

On the command line the lifecycle is the `coffer agent` group's verbs — `list`, `show <type>`, `add <type> [--config-dir <dir>]`, `edit <type>` (with `--config-dir` and the model options of "Carry the model binding on the agent record"), `rm`, `enable` and `disable`, each taking the type (or a uid). The `agent` kind has no `scope` verb, because it declares no scope. `coffer agent show <type>` MUST print the agent's record together with one derived state, `coffer_connection`: the agent's Coffer connection part by part ("Report an agent's Coffer connection part by part"), in the shape `GET /api/v1/agents/{uid}/coffer-connection` answers — its state and, for each applicable part (the gateway MCP entry, and the memory delivery hook while memory is on), whether it is installed.

#### Scenario: register an agent without an explicit name
- **GIVEN** the daemon is running and no `claude_code` agent is registered
- **WHEN** the user runs `coffer agent add claude-code`, supplying only the type
- **THEN** the agent is registered under the type's name `claude-code` (underscores become hyphens) at the type's standard config directory, audited as `resource_created`

#### Scenario: update an existing agent
- **GIVEN** a registered agent
- **WHEN** the user updates its `config_dir` to a new writable path
- **THEN** the change persists, an audit entry is recorded, and subsequent operations see the new path

#### Scenario: remove an agent
- **GIVEN** a registered agent (any binding cleanup is handled by the skill-manager spec)
- **WHEN** the user removes it
- **THEN** the agent is deleted, an audit entry is recorded, and `coffer agent list` no longer shows it

#### Scenario: use a different config directory from the command line
- **GIVEN** a registered agent `claude-code` at `~/.claude` and another writable directory
- **WHEN** the user runs `coffer agent edit claude-code --config-dir <dir>`
- **THEN** `coffer agent show claude-code` reports `<dir>` as its config directory, with the same uid and name
- **AND** `coffer agent edit` offers no `--name`, `--title` or `--description`

#### Scenario: give an agent a title from the command line
- **GIVEN** a registered agent named `claude-code`
- **WHEN** the user runs `coffer agent edit claude-code --title "Work laptop Claude"`, and submits the same title through the kind-agnostic update route
- **THEN** the command exits non-zero on the unknown option and the route refuses the title as a validation error (422)
- **AND** `coffer agent show claude-code` still shows the agent as `claude-code`, with its uid and no title

### Requirement: Validate the config directory at registration
At registration the system MUST auto-create the `<config_dir>/skills` subdirectory, then validate that the resolved `config_dir` exists — or, for the standard config directory of a type in state `installed_never_run`, create it first, holding only the entries Coffer needs — is a directory, is writable, and is not a privileged system path before accepting the value. The privileged locations are `/etc`, `/bin`, `/sbin`, `/usr`, `/var`, `/sys`, `/proc`, `/root`, `/boot`, `/dev`, `/System` and `/Library/Application Support/Apple` on POSIX hosts — matched at a path-component boundary, after resolving symlinks and stripping macOS's `/private` firmlink prefix, with the user temp area under `/var/folders/` carved out as usable — and `C:\Windows`, `C:\Program Files` and `C:\Program Files (x86)` on Windows. A rejected registration leaves no partial state, and no `config_dir` value may permit writing outside the directory itself.

#### Scenario: reject registration with an invalid config dir
- **GIVEN** the daemon is running
- **WHEN** the user registers an agent whose `config_dir` does not exist, is not a directory, or is not writable
- **THEN** registration is rejected with a message naming the path, and nothing is persisted

#### Scenario: reject registration into privileged system path
- **GIVEN** the daemon is running
- **WHEN** the user attempts to register an agent whose `config_dir` resolves under a privileged location (e.g. `/etc`, `/usr`, `/var` outside `/var/folders/`, `/System`, `C:\Windows`, or `C:\Program Files`)
- **THEN** registration is rejected with `unprocessable_entity` (422) and no resource row, audit event, or filesystem write occurs

#### Scenario: register an agent with a custom config dir
- **GIVEN** the daemon is running
- **WHEN** the user registers an agent of supported type with an explicit, writable `config_dir`
- **THEN** the agent is persisted with that path (and its `<config_dir>/skills` subdirectory auto-created) and appears in `coffer agent list`

#### Scenario: register an installed agent whose config directory is not created yet
- **GIVEN** Codex's program is on its `PATH`, `~/.codex` does not exist and no `codex` agent is registered
- **WHEN** the user registers a `codex` agent without a config directory
- **THEN** `~/.codex` is created holding only its `skills` directory, and the agent is registered there
- **AND** registering a type whose program is not installed on a directory that does not exist is still rejected, with nothing created

### Requirement: Allow one agent per name and per config directory
The system MUST reject registration that would create a duplicate agent name (409 `conflict`, as for any kind) — which, because an agent's name is its type's, is one agent per type ("Keep one agent per type, named by it") — and MUST reject registering more than one agent for the same config directory. The check compares resolved config directories — a registration without a `config_dir` resolves to its type's standard location — and runs on every move of an agent's directory too. A second agent for a directory already registered is rejected with `conflict` (409) and nothing is persisted.

#### Scenario: reject duplicate agent name
- **GIVEN** an agent named `codex` exists
- **WHEN** the user attempts to register another agent of type `codex`, whose name would be the same
- **THEN** registration is rejected with a clear error and nothing is persisted

#### Scenario: reject a second agent for an already-registered config dir
- **GIVEN** a `codex` agent is registered with the config dir `/tmp/shared`
- **WHEN** the user attempts to register a `claude_code` agent, or to move another agent, to a config dir that resolves to `/tmp/shared`
- **THEN** the request is rejected with a clear error and nothing is persisted — only one agent may exist per config directory

### Requirement: Offer JSON output on every CLI read
The CLI MUST support `--json` for machine-readable output on every read operation.

#### Scenario: agent reads print JSON with --json
- **GIVEN** a registered agent
- **WHEN** the user runs `coffer agent list --json` and `coffer agent show <type> --json`
- **THEN** each prints only JSON, carrying the agent's name, display name, type and config directory, and `show` also its uid and its `coffer_connection` status

### Requirement: Expose agent discovery on every surface
The system MUST expose a read-only discovery operation listing the supported types seen on this machine that have no agent registered, as candidates — at most one per type — available from the REST API (`GET /api/v1/agents/candidates`, rows shaped as "Report every supported type's detection state" describes), the `coffer scan` CLI (as rows of kind `agent`), and the Agents page in the web UI, where the user adds an addable candidate — `installed_active`, or `installed_never_run`, whose standard directory registration creates — with a single confirm and no typing of type identifiers, names or paths; a `config_only` one is shown as not installed, with no add action. On the command line an addable candidate is registered with the `coffer agent add <type>` command its scan row names.

#### Scenario: list discovery candidates from the command line
- **GIVEN** a supported agent is installed with its standard config directory present and no agent of that type is registered
- **WHEN** the user runs `coffer scan`
- **THEN** the command lists that type as a row of kind `agent` with its config dir, its state and its version
- **AND** no agent is registered as a result

### Requirement: Detect an agent by its program and its config directory
The system MUST detect an agent from two signals: its program on the agent's real `PATH` — the user's login-shell `PATH` merged with the daemon's inherited one, asked through the platform layer — together with the version that program reports, and its config directory on disk. The version MUST be read with the program's own version flag under a bounded timeout, and detection MUST NOT run anything that needs a login, a network call or the agent's config. The two signals MUST be named as one state: `installed_active` (program and directory), `installed_never_run` (program, no directory yet), `config_only` (directory, program missing) and `missing` (neither). Discovery candidates, the per-type listing of "Report every supported type's detection state" and every registered agent read (`GET /api/v1/agents`, `GET /api/v1/agents/{uid}`, `coffer agent show`) MUST carry the state and the version, read at request time and never stored. A `config_only` agent is shown as not installed.

#### Scenario: read the installed program's version
- **GIVEN** the agent's program is on the agent's `PATH` and answers its version flag with `2.1.281 (Claude Code)`
- **WHEN** the agent is detected
- **THEN** the program is found and its version is `2.1.281`
- **AND** a program that does not answer within the bound is still found, with no version

#### Scenario: offer an installed agent that has never run
- **GIVEN** a supported agent's program is on its `PATH` and its standard config directory does not exist
- **WHEN** the user runs discovery
- **THEN** that type is a candidate in state `installed_never_run`, with its standard config directory, and is offered for adding

#### Scenario: show a leftover config directory as not installed
- **GIVEN** a supported agent's standard config directory exists and its program is not on its `PATH`
- **WHEN** the user runs discovery
- **THEN** that type is a candidate in state `config_only`, with no version, and is not offered for adding

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

### Requirement: Discover agents on this machine as candidates without registering them
The system MUST provide a read-only discovery operation that looks, for each supported type, at its standard config directory — named in that type's child spec — and at the directory that type's own environment variable (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`) names in the daemon's environment when set, and reports each type with no agent registered and with either detection signal of "Detect an agent by its program and its config directory" as one **candidate**, carrying the fields of "Report every supported type's detection state". Nothing else is scanned. Candidates are derived at scan time and never stored. Discovery MUST NOT register anything automatically — the user reviews candidates and confirms which to add, and an `installed_active` or `installed_never_run` candidate can be added — the second's registration creates its standard config directory with only the entries Coffer needs — while a `config_only` candidate cannot, because a directory whose program is gone belongs to no working agent. The daemon MUST NOT auto-register agents on startup.

On the command line, candidates are rows of kind `agent` in `coffer scan`, the one listing of everything agents hold that Coffer does not manage yet (see [resource-framework](../resource-framework/spec.md), the requirement that defines `coffer scan`, `coffer adopt` and `coffer discard`). Each row MUST carry the candidate's state and version; an addable row MUST name the `coffer agent add <type>` command that registers it — with `--config-dir` only for a directory other than the standard one — through the ordinary registration of "Manage the agent lifecycle", and any other row says why it cannot be added. A candidate MUST NOT be discardable: nothing of Coffer's put the agent there, so neither `coffer adopt` nor `coffer discard` offers an `agent` command.

#### Scenario: discover installed agents as candidates
- **GIVEN** a Coffer install with a supported agent's program installed, its standard config directory present, and no agent registered
- **WHEN** the user runs discovery
- **THEN** Coffer reports that type as an `installed_active` candidate (type, name, display name, config dir, version, addable) and registers nothing — discovery is read-only

#### Scenario: skip already-registered config directories on subsequent scan
- **GIVEN** a `codex` agent is registered for `~/.codex`, and `CODEX_HOME` names another existing directory
- **WHEN** the user runs discovery again
- **THEN** no `codex` candidate is offered, for either directory, because the type already has its agent

#### Scenario: adopt a discovered agent from the command line
- **GIVEN** Codex is installed, `~/.codex` is present and no `codex` agent is registered
- **WHEN** the user runs `coffer scan`, then `coffer agent add codex`
- **THEN** the scan lists a row of kind `agent` for `codex` that names `coffer agent add codex`, and registers nothing
- **AND** the add registers the `codex` agent at the default config directory, audited as `resource_created`
- **AND** neither `coffer adopt` nor `coffer discard` offers an `agent` command

## REMOVED Requirements

### Requirement: Serve each agent type's model catalogue
**Reason**: Two agents of one type can no longer be registered, so which of them answers is no longer a rule; the requirement is replaced by "Serve each agent type's model catalogue from its one agent".
**Migration**: None for callers — the route and its answer are unchanged.
