# Agent Registry — Codex

## Purpose
This child of [`agent-registry`](../spec.md) says how the `codex` agent type realises each facet its parent defines: where its config directory is, which of its files Coffer may read and write and which it must never touch, the shape of the MCP entry Coffer installs, where its plugin entries and cache live, how its model catalogue and reasoning levels are read back, the one value its `wire_api` binding accepts, where it keeps its own memory, and where it writes its transcripts. It is the prose reading of that type's one `AGENT_DESCRIPTORS` record — default config dir `~/.codex/`, its allowlist and credential exclusion, its injection spec, a `PluginCapability` whose uninstall strategy is a config edit, its native-memory layout, its transcript location and its catalogue sources. Everything the two supported types share, and everything the parent assumes, lives in the parent and is not restated here.

"Codex" is the product: its CLI and its IDE form together, because they read one shared config directory. `config.toml` is the single file behind most of this type's facets — MCP entries, plugins, marketplaces, configured models — so one parse failure degrades all of them at once to the parent's parse-error state. Codex keeps its plugin entries and marketplaces in that same file, with each plugin's content in a cache directory; Coffer toggles one documented field and, on uninstall, removes the entry and the cache together.

## Requirements

### Requirement: Locate Codex at ~/.codex
The `codex` type's standard config directory MUST be `~/.codex/`, which is the value `config_dir` defaults to under [agent-registry](../spec.md) "Validate agent configuration against the agent schema". The presence of that directory MUST be the install marker [agent-registry](../spec.md) "Discover installed agents as candidates without registering them"'s discovery scans for, and [agent-registry](../spec.md) "Allow one agent per name and per config directory"'s one-agent-per-config-directory rule follows from it: Codex is registrable once unless the user overrides the path. An overridden `config_dir` is the directory Codex is run against through its `CODEX_HOME` environment variable — the only way Codex reads a home other than `~/.codex`, and the root of its `config.toml`, `auth.json`, sessions and memories. Every Codex process Coffer itself starts for such an agent — a chat or channel turn, per [chat](../../chat/spec.md) "Ship Claude Code and Codex subprocess providers", and the `model/list` probe of "Read Codex models from model/list and config.toml" — MUST carry `CODEX_HOME=<config_dir>`; for the default `~/.codex` the variable is left unset.

#### Scenario: discover Codex by its config directory
- **GIVEN** a home directory containing `~/.codex/` and no agent registered
- **WHEN** the user runs discovery
- **THEN** a `codex` candidate is reported whose `config_dir` is `~/.codex`
- **AND** a `codex` agent registered without a `config_dir` resolves to `~/.codex`

### Requirement: Allowlist exactly Codex's config, instructions and hooks files
The curated allowlist ([agent-registry](../spec.md) "Define a curated config-file allowlist per type") for `codex` MUST be exactly: `config.toml` (format `toml`), `AGENTS.md` under the key `instructions`, and `hooks.json`. This type has no directory entry. `AGENTS.md` is human-authored instructions and its key says so; the agent's own written memory is the scan of "Scan Codex's global task-grouped memory" and memory's domain, not this file.

#### Scenario: list exactly Codex's three config files
- **GIVEN** a registered `codex` agent
- **WHEN** the user lists its config files
- **THEN** exactly three entries are returned — `config.toml` (format `toml`), `AGENTS.md` under the key `instructions`, and `hooks.json`
- **AND** none of them is a directory entry

### Requirement: Never expose Codex's credential file
`<config_dir>/auth.json` MUST never enter the allowlist, any config-file listing, or any facet's parse. It is a credential file: it is not readable through [agent-registry](../spec.md) "Read allowlisted config files without creating them" because it is not an allowlisted key, and neither the MCP-entry nor the plugin parser opens it.

#### Scenario: refuse to read auth.json
- **GIVEN** a registered `codex` agent whose config directory holds an `auth.json`
- **WHEN** the user lists the agent's config files and then requests `auth.json` by key
- **THEN** the listing does not include it
- **AND** the request is refused `404 CONFIG_FILE_NOT_ALLOWED` with no filesystem read

### Requirement: Install Coffer's MCP entry into config.toml preserving its layout
The `McpInjectionSpec` [agent-registry](../spec.md) "Install Coffer's MCP server into an agent in one action" installs through MUST write `[mcp_servers.coffer]` in `config.toml`, whose `command` is the resolved absolute shim path and whose `args` are `["--agent-uid", "<uid>"]` — the same command-map shape Claude Code's entry uses. Edits to this file MUST preserve the user's comments and key ordering, which is why it is edited as TOML rather than reserialized.

#### Scenario: install Coffer's MCP into config.toml keeping the user's comments
- **GIVEN** a registered `codex` agent whose `config.toml` carries comments and other tables
- **WHEN** the user installs Coffer's MCP
- **THEN** `[mcp_servers.coffer]` is written with `command` set to the absolute shim path and `args` set to `--agent-uid` and the agent's uid
- **AND** the user's comments and the other tables are preserved

### Requirement: Report but never write Codex MCP entries' enabled flag
The entries [agent-registry](../spec.md) "List the MCP entries in the agent's own config files" lists MUST be parsed from `config.toml` `[mcp_servers.*]`, the one source file for this type. This format defines a per-entry `enabled` flag, so `enabled` MUST be reported for these entries — and MUST NOT be written: flipping it duplicates a switch Codex's own UI already owns, and the parent's refusal to toggle an entry's `enabled` flag is the rule this obeys.

#### Scenario: report the enabled flag of Codex MCP entries
- **GIVEN** a registered `codex` agent whose `config.toml` has one `[mcp_servers.*]` entry with `enabled = false` and one without the key
- **WHEN** the user lists the agent's MCP entries
- **THEN** both entries are labelled with `config.toml` as their source
- **AND** the first reports `enabled=false` and the second `enabled=true`

### Requirement: Read Codex plugins from config.toml and the cache directory
The inventory [agent-registry](../spec.md) "List an agent's installed plugins without writing anything" lists MUST be derived from `config.toml`'s `[plugins."<name>@<marketplace>"]` tables and `[marketplaces.*]` tables, with `cache_present` from the presence of the documented cache directory `<config_dir>/plugins/cache/<marketplace>/<plugin>/`.

#### Scenario: flag a Codex plugin without its cache directory
- **GIVEN** a registered `codex` agent whose `config.toml` declares two plugins of one marketplace, only one of which has its `plugins/cache/<marketplace>/<plugin>/` directory
- **WHEN** the user lists the agent's plugins
- **THEN** both plugins are listed with that marketplace
- **AND** only the one with a cache directory reports `cache_present=true`

### Requirement: Toggle a Codex plugin's own enabled field only
The toggle of [agent-registry](../spec.md) "Toggle a plugin through the documented location only" MUST write only the plugin entry's own `enabled` field in `config.toml`. No other table in that file, and no file under `plugins/`, may change.

#### Scenario: toggle a Codex plugin by its enabled field
- **GIVEN** a registered `codex` agent with an enabled plugin in `config.toml`
- **WHEN** the user disables it
- **THEN** that plugin's table carries `enabled = false`
- **AND** every other table in `config.toml` is unchanged

### Requirement: Uninstall a Codex plugin by editing config.toml
The uninstall strategy of [agent-registry](../spec.md) "Uninstall a plugin by the type's own strategy" for this type MUST be a config edit: remove the `[plugins."…"]` entry from `config.toml` (atomic, with the `.bak` of [agent-registry](../spec.md) "Write config files atomically with a backup and an audit entry") and delete that plugin's cache directory. There is no CLI to delegate to and none is required, so `can_uninstall` is true whenever the entry exists.

#### Scenario: uninstall a Codex plugin
- **GIVEN** a registered `codex` agent with an installed plugin
- **WHEN** the user uninstalls it
- **THEN** the `[plugins."…"]` entry is removed from `config.toml` (atomic + `.bak`), the plugin's cache directory under `~/.codex/plugins/cache/` is deleted, and an `agent_plugin_uninstalled` audit entry is recorded

### Requirement: Read Codex models from model/list and config.toml
The catalogue sources of [agent-registry](../spec.md) "Read the model catalogue back from the installed agent" for this type MUST be Codex's own `model/list` app-server RPC, plus the models configured in `config.toml` as the native-config contribution of [agent-registry](../spec.md) "Contribute models from the type's native config read-only". The RPC is reachable only when the CLI is installed and authenticated, so it is one degradable source, never a precondition of the response: an unauthenticated or wedged agent answers nothing over RPC and costs exactly those entries. The RPC is asked of the Codex whose home is the agent's config directory ("Locate Codex at ~/.codex"), and its answer is held per config directory, never shared between two: two homes can be two logins.

#### Scenario: fall back to configured models when model/list answers nothing
- **GIVEN** a `codex` config directory whose `config.toml` names a model, and a Codex CLI whose `model/list` RPC cannot be reached
- **WHEN** the Codex catalogue sources are read in order
- **THEN** the configured model is offered
- **AND** no RPC entry appears and the read does not fail

#### Scenario: ask model/list of the agent's own Codex home
- **GIVEN** a `codex` agent registered with a `config_dir` other than `~/.codex`
- **WHEN** the Codex catalogue sources are read for it
- **THEN** the `model/list` app-server is started with `CODEX_HOME` set to that `config_dir`, the rest of the daemon's environment intact
- **AND** a probe for the default `~/.codex` starts with the environment untouched, and neither directory's answer is served for the other

### Requirement: Carry each Codex model's own effort levels and default
The runtime source of [agent-registry](../spec.md) "Read reasoning-effort levels from the agent runtime" for this type MUST be per model: `model/list` reports `supportedReasoningEfforts` and a `defaultReasoningEffort` per entry, so each catalogue entry carries its own levels and its own default. The default is kept only when it is one of the levels that entry offers.

#### Scenario: drop a default effort the model does not offer
- **GIVEN** a `model/list` answer with two models, the first reporting levels `low` and `high` with default `low`, the second reporting only `medium` with a default of `xhigh`
- **WHEN** the Codex catalogue is read
- **THEN** each entry carries its own reported levels
- **AND** the first keeps `low` as its default while the second reports no default

### Requirement: Accept only responses as Codex's wire_api
`responses` MUST be the only accepted value of the `wire_api` field [agent-registry](../spec.md) "Carry the model binding on the agent record" puts on the agent record, enforced where the binding is validated so that anything else is a 422 the user sees at the moment they set it, with nothing persisted or projected. Codex does not merely ignore another value — it **refuses to load `config.toml`**, so an agent Coffer projected into would have a CLI that will not start. This MUST NOT be fixed by remapping the value at projection time: rewriting it on the way out would leave the stored value, and every read of the agent reporting it, saying something other than what Coffer projects, and a setting must not lie about itself. With one legal value the per-agent override can only hold its own default, which makes the field vestigial; retiring it is a separate change, since it is on the public API and the contract.

#### Scenario: reject a wire_api other than responses
- **GIVEN** a registered `codex` agent
- **WHEN** the user sets its `wire_api` to `chat`
- **THEN** the request is rejected with `unprocessable_entity` (422)
- **AND** the agent's stored `wire_api` is unchanged

### Requirement: Scan Codex's global task-grouped memory
The native-memory layout of [agent-registry](../spec.md) "Scan an agent's own native memory stores read-only" for this type MUST be a single GLOBAL task-grouped document at `<config_dir>/memories/MEMORY.md`, where each `# Task Group` block carries an `applies_to: cwd=…` line routing it to one or more project working directories. The scan MUST parse it into one row per distinct routed cwd, with `path` and `project` that cwd, `item_count` the number of Task Groups routed there, and `memory_dir` the one shared global store repeated on every row. An absent document yields an empty list, and a Task Group with no `applies_to: cwd=` line routes to no project and produces no row.

#### Scenario: the native memory scan lists Codex's global memory by project
- **GIVEN** a registered `codex` agent whose `<config_dir>/memories/MEMORY.md` holds `# Task Group` blocks, each with an `applies_to: cwd=…` line routing it to one or more project working directories
- **WHEN** the user scans the agent's native memory
- **THEN** Coffer parses the single global document into one store row per distinct routed cwd — `project`/`path` the cwd, `item_count` the number of Task Groups routed there, and `memory_dir` the one shared global store — read-only and emitting no audit event; with no `memories/MEMORY.md` the list is empty

### Requirement: Read Codex transcripts from the sessions directory
The transcript location of [agent-registry](../spec.md) "List an agent's transcript sessions read-only" for this type MUST be `<config_dir>/sessions/**/*.jsonl`.

#### Scenario: list Codex sessions from the sessions directory
- **GIVEN** a registered `codex` agent with a session `.jsonl` nested under `<config_dir>/sessions/`
- **WHEN** the user lists the agent's transcripts
- **THEN** that session is listed with its file's absolute path as `source_path`

### Requirement: Leave Codex's internal-state tables untouched
The internal-state tables this type keeps in `config.toml` — `[marketplaces.*]`, `[hooks.state.*]` and `[projects.*]` — are the Codex side of the parent's "internal state files are read as inputs and never written". They MUST be read where a facet needs them ("Read Codex plugins from config.toml and the cache directory" reads the marketplaces) and MUST be byte-identical before and after every write Coffer makes to that file; every such write also preserves the user's comments and key ordering.

#### Scenario: keep internal-state tables byte-identical across every write
- **GIVEN** a registered `codex` agent whose `config.toml` carries `[marketplaces.*]`, `[hooks.state.*]` and `[projects.*]` tables beside a plugin and a direct MCP entry
- **WHEN** Coffer installs its MCP, toggles the plugin, uninstalls the plugin and removes the MCP entry
- **THEN** after each write the text of those three tables is byte-identical to the original
