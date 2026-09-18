# Feature Specification: Agent Registry — Codex

**Status**: Accepted
**Input**: How the `codex` agent type realises each facet its parent spec defines: where its config directory is, which of its files Coffer may read and write and which it must never touch, the shape of the MCP entry Coffer installs, where its plugin entries and cache live, how its model catalogue and reasoning levels are read back, the one value its `wire_api` binding accepts, where it keeps its own memory, and where it writes its transcripts.

> **Parent spec.** [`agent-registry`](../spec.md) owns everything the two supported agent types share — the resource model, discovery, lifecycle, the config-file read/write contract, MCP install, MCP entries, plugins, directory entries, the model-catalogue contract, the native-memory scan, transcripts and the surfaces. This spec holds only what is specific to OpenAI Codex, and is the prose reading of that type's one `AGENT_DESCRIPTORS` record. Cite a requirement here as `agent-registry/codex FR-00N`.

> **Scope note.** "Codex" here is the product: its CLI and its IDE form together, because they read one shared config directory.

## User Scenarios & Testing

### User Story 1 — Register the Codex that is already installed (Priority: P1)

The user has Codex installed. Coffer finds it by the presence of its config directory, offers it as a candidate, and after one confirm manages that directory's curated files.

**Independent Test**: With `~/.codex/` present and no agent registered, run discovery and observe a `codex` candidate whose `config_dir` is `~/.codex`; confirm it and observe the agent registered.

### User Story 2 — Edit the files Codex actually reads, and none of the ones it hides (Priority: P2)

The user opens the agent's Config files tab and finds its TOML config, its instructions file and its hooks file — and does not find its credential file, which never enters any listing.

**Independent Test**: List the agent's config files and observe exactly three entries; request the credential file by key and observe a 404 with no filesystem read.

### User Story 3 — Manage the plugins Codex installed (Priority: P2)

Codex keeps both its plugin entries and its marketplaces in the same TOML file it keeps everything else in, with the plugin's content in a cache directory. Coffer toggles one documented field and, on uninstall, removes the entry and the cache together.

**Independent Test**: With plugins configured, list them; disable one and observe `enabled = false` written to `config.toml` with the rest of the file's comments and ordering intact; uninstall one and observe its entry and its cache directory gone.

### Edge Cases

- **`config.toml` fails to parse**: Every facet that reads it — MCP entries, plugins, the configured-models catalogue source — degrades to the parse-error state of agent-registry FR-023 at once, because they all read one file.
- **`wire_api` set to anything but `responses`**: Rejected at the moment it is set, with a 422 the user sees then rather than a CLI that will not start later.
- **`memories/MEMORY.md` absent**: The native-memory scan returns an empty list; the global document is the only store this type has.
- **A Task Group with no `applies_to: cwd=` line**: It routes to no project and therefore produces no store row; nothing is invented for it.

## Acceptance Scenarios

Every scenario here is referenced by at least one test marked `@pytest.mark.acceptance(spec="agent-registry/codex", scenario="…")` (Python) or `acceptance("agent-registry/codex", "…", …)` (TypeScript).

### Scenario: uninstall a Codex plugin

- **Given** a registered `codex` agent with an installed plugin,
- **When** the user uninstalls it,
- **Then** the `[plugins."…"]` entry is removed from `config.toml` (atomic + `.bak`), the plugin's cache directory under `~/.codex/plugins/cache/` is deleted, and an `agent_plugin_uninstalled` audit entry is recorded.

### Scenario: the native memory scan lists Codex's global memory by project

- **Given** a registered `codex` agent whose `<config_dir>/memories/MEMORY.md` holds `# Task Group` blocks, each with an `applies_to: cwd=…` line routing it to one or more project working directories,
- **When** the user scans the agent's native memory,
- **Then** Coffer parses the single global document into one store row per distinct routed cwd — `project`/`path` the cwd, `item_count` the number of Task Groups routed there, and `memory_dir` the one shared global store — read-only and emitting no audit event; with no `memories/MEMORY.md` the list is empty.

## Requirements

### Functional Requirements

**Identity and location**

- **FR-001**: The `codex` type's standard config directory MUST be `~/.codex/`, which is the value `config_dir` defaults to under agent-registry FR-002. The presence of that directory MUST be the install marker agent-registry FR-004's discovery scans for, and agent-registry FR-008's one-agent-per-config-directory rule follows from it: Codex is registrable once unless the user overrides the path.

**Config files**

- **FR-002**: The curated allowlist (agent-registry FR-009) for `codex` MUST be exactly: `config.toml` (format `toml`), `AGENTS.md` under the key `instructions`, and `hooks.json`. This type has no directory entry. `AGENTS.md` is human-authored instructions and its key says so; the agent's own written memory is FR-012's scan and spec memory's domain, not this file.
- **FR-003**: `<config_dir>/auth.json` MUST never enter the allowlist, any config-file listing, or any facet's parse. It is a credential file: it is not readable through agent-registry FR-011 because it is not an allowlisted key, and neither the MCP-entry nor the plugin parser opens it.

**Coffer MCP install**

- **FR-004**: The `McpInjectionSpec` agent-registry FR-015 installs through MUST write `[mcp_servers.coffer]` in `config.toml`, a typed-array entry whose first element is the resolved absolute shim path and whose `--agent-uid <uid>` argument is APPENDED to that `command` array. Edits to this file MUST preserve the user's comments and key ordering, which is why it is edited as TOML rather than reserialized.

**Agent MCP entries**

- **FR-005**: The entries agent-registry FR-019 lists MUST be parsed from `config.toml` `[mcp_servers.*]`, the one source file for this type. This format defines a per-entry `enabled` flag, so `enabled` MUST be reported for these entries — and MUST NOT be written: flipping it duplicates a switch Codex's own UI already owns, and agent-registry's "Not provided: toggling an entry's `enabled` flag" is the rule this obeys.

**Plugins**

- **FR-006**: The inventory agent-registry FR-024 lists MUST be derived from `config.toml`'s `[plugins."<name>@<marketplace>"]` tables and `[marketplaces.*]` tables, with `cache_present` from the presence of the documented cache directory `<config_dir>/plugins/cache/<marketplace>/<plugin>/`.
- **FR-007**: The toggle of agent-registry FR-025 MUST write only the plugin entry's own `enabled` field in `config.toml`. No other table in that file, and no file under `plugins/`, may change.
- **FR-008**: The uninstall strategy of agent-registry FR-026 for this type MUST be a config edit: remove the `[plugins."…"]` entry from `config.toml` (atomic, with the `.bak` of agent-registry FR-013) and delete that plugin's cache directory. There is no CLI to delegate to and none is required, so `can_uninstall` is true whenever the entry exists.

**The model catalogue**

- **FR-009**: The catalogue sources of agent-registry FR-033 for this type MUST be Codex's own `model/list` app-server RPC, plus the models configured in `config.toml` as the native-config contribution of agent-registry FR-035. An unauthenticated or wedged agent answers nothing over RPC and costs exactly those entries.

**Reasoning effort levels**

- **FR-010**: The runtime source of agent-registry FR-037 for this type MUST be per model: `model/list` reports `supportedReasoningEfforts` and a `defaultReasoningEffort` per entry, so each catalogue entry carries its own levels and its own default. The default is kept only when it is one of the levels that entry offers.

**The model binding's `wire_api`**

- **FR-011**: `responses` MUST be the only accepted value of the `wire_api` field agent-registry FR-031 puts on the agent record, enforced where the binding is validated so that anything else is a 422 the user sees at the moment they set it. Codex does not merely ignore another value — it **refuses to load `config.toml`**, so an agent Coffer projected into would have a CLI that will not start. This MUST NOT be fixed by remapping the value at projection time: rewriting it on the way out would leave the stored value, and every read of the agent reporting it, saying something other than what Coffer projects, and a setting must not lie about itself. With one legal value the per-agent override can only hold its own default, which makes the field vestigial; retiring it is a separate change, since it is on the public API and the contract.

**Native memory**

- **FR-012**: The native-memory layout of agent-registry FR-039 for this type MUST be a single GLOBAL task-grouped document at `<config_dir>/memories/MEMORY.md`, where each `# Task Group` block carries an `applies_to: cwd=…` line routing it to one or more project working directories. The scan MUST parse it into one row per distinct routed cwd, with `path` and `project` that cwd, `item_count` the number of Task Groups routed there, and `memory_dir` the one shared global store repeated on every row. An absent document yields an empty list.

**Transcripts**

- **FR-013**: The transcript location of agent-registry FR-040 for this type MUST be `<config_dir>/sessions/**/*.jsonl`.

**Internal state, never written**

- **FR-014**: The internal-state tables this type keeps in `config.toml` — `[marketplaces.*]`, `[hooks.state.*]` and `[projects.*]` — are the Codex side of the parent spec's "internal state files are read as inputs and never written". They MUST be read where a facet needs them (FR-006 reads the marketplaces) and MUST be byte-identical before and after every write Coffer makes to that file.

### Key Entities

- **`codex` descriptor**: The `AGENT_DESCRIPTORS` record this spec reads — default config dir `~/.codex/`, the FR-002 allowlist with FR-003's exclusion, the FR-004 injection spec, a `PluginCapability` whose uninstall strategy is the config edit of FR-008, the FR-012 native-memory layout, the FR-013 transcript location, and the FR-009 catalogue sources.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Every Acceptance Scenario in this spec is covered by at least one test marked `acceptance(spec="agent-registry/codex", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.
- **SC-002**: Every write Coffer makes to `config.toml` preserves the user's comments, key ordering and every table FR-014 names, verified by a test that diffs the file around each write.
- **SC-003**: Setting `wire_api` to any value other than `responses` is refused with a 422 and nothing is persisted or projected.

## Assumptions

- `config.toml` is the single file behind most of this type's facets — MCP entries, plugins, marketplaces, configured models — so one parse failure degrades all of them at once, which the parse-error state of agent-registry FR-023 already covers.
- Codex's `model/list` app-server RPC is reachable only when the CLI is installed and authenticated; the catalogue treats it as one degradable source, never a precondition of the response.
- Everything the parent spec assumes applies here unchanged; this spec restates none of it.
