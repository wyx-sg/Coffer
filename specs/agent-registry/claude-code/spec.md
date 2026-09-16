# Feature Specification: Agent Registry — Claude Code

**Status**: Accepted
**Input**: How the `claude_code` agent type realises each facet its parent spec defines: where its config directory is, which of its files Coffer may read and write, the shape of the MCP entry Coffer installs, where its plugin inventory and enabled state live, how its model catalogue and reasoning levels are read back, where it keeps its own memory, and where it writes its transcripts.

> **Parent spec.** [`agent-registry`](../spec.md) owns everything the two supported agent types share — the resource model, discovery, lifecycle, the config-file read/write contract, MCP install, MCP entries, plugins, directory entries, the model-catalogue contract, the native-memory scan, transcripts and the surfaces. This spec holds only what is specific to Claude Code, and is the prose reading of that type's one `AGENT_DESCRIPTORS` record. Cite a requirement here as `agent-registry/claude-code FR-00N`.

> **Scope note.** "Claude Code" here is the product: its CLI and its IDE/desktop form together, because they read one shared config directory. The separate **Claude Desktop** chat app has its own config directory and is not this type.

## User Scenarios & Testing

### User Story 1 — Register the Claude Code that is already installed (Priority: P1)

The user has Claude Code installed. Coffer finds it by the presence of its config directory, offers it as a candidate, and after one confirm manages that directory's curated files.

**Independent Test**: With `~/.claude/` present and no agent registered, run discovery and observe a `claude_code` candidate whose `config_dir` is `~/.claude`; confirm it and observe the agent registered.

### User Story 2 — Edit the files Claude Code actually reads (Priority: P2)

The user opens the agent's Config files tab and finds exactly the files Claude Code reads — its settings, its user-level `~/.claude.json`, the instructions file, and the directory of personal subagents — rather than every dotfile under the directory.

**Independent Test**: List the agent's config files and observe the curated set with each file's resolved path, format, and existence.

### User Story 3 — Manage the plugins Claude Code installed (Priority: P2)

Claude Code keeps its plugin inventory in files it owns and its enabled state in a file the user owns. Coffer reads the first, writes only the second, and hands an uninstall to Claude Code's own CLI.

**Independent Test**: With plugins installed, list them; disable one and observe only the enabled-state map changed; uninstall one and observe Coffer ran the CLI rather than editing the inventory.

### Edge Cases

- **The same MCP entry name in both source files**: Both entries are listed, each labelled with its source file; a remove or adopt request carries the source so the right one is acted on.
- **The embedded model table cannot be located**: The alias source contributes nothing and the catalogue answers from the remaining sources — it does not fall back to a list Coffer wrote down.
- **A project's transcripts are gone but its memory directory remains**: The store still lists; its `project` label falls back to a lossy decode of the directory slug, which is why the real path is preferred whenever a transcript can supply it.
- **`additionalModelOptionsCache` holds stale entries**: It is read as one catalogue source and never written — Claude Code owns that key and clobbers anything Coffer put there.

## Acceptance Scenarios

Every scenario here is referenced by at least one test marked `@pytest.mark.acceptance(spec="agent-registry/claude-code", scenario="…")` (Python) or `acceptance("agent-registry/claude-code", "…", …)` (TypeScript).

### Scenario: list an agent's config files

- **Given** a registered `claude_code` agent,
- **When** the user lists its config files,
- **Then** Coffer returns the curated set for the type — `settings.json`, `settings.local.json`, `~/.claude.json`, `CLAUDE.md` (key `instructions`), and the `agents/` directory entry — each with its resolved path, its containing-folder absolute path (`folder_path`), format, and an `exists` flag (with size + modified time when present).

### Scenario: install Coffer's MCP into an agent

- **Given** a registered `claude_code` agent and a resolvable `coffer-mcp-shim` binary,
- **When** the user installs Coffer's MCP,
- **Then** a `coffer` entry is written into `~/.claude.json` `mcpServers` with `command` set to the absolute shim path, the prior file is backed up to `.bak`, an `agent_mcp_installed` audit entry is recorded, and install status reports `installed=true`.

### Scenario: uninstall a Claude Code plugin via its CLI

- **Given** a registered `claude_code` agent with an installed plugin and the `claude` CLI on PATH,
- **When** the user uninstalls it,
- **Then** Coffer runs `claude plugin uninstall <id>` (it never hand-writes Claude's internal `installed_plugins.json` / `settings.json`), the request succeeds, and an `agent_plugin_uninstalled` audit entry is recorded.

### Scenario: reject Claude uninstall when its CLI is unavailable

- **Given** a registered `claude_code` agent whose `claude` CLI is not on PATH,
- **When** the user attempts to uninstall a plugin,
- **Then** the request is rejected with `unprocessable_entity` (422) and error code `PLUGIN_UNINSTALL_UNSUPPORTED`, and nothing is written — the listing also hides the in-app uninstall affordance in this case.

### Scenario: the native memory scan lists an agent's own per-project stores

- **Given** a registered `claude_code` agent whose `<config_dir>/projects/<slug>/memory` directory holds `.md` fact files (plus a `MEMORY.md` index),
- **When** the user scans the agent's native memory,
- **Then** Coffer returns one store per project with a `project` label and `path` that are the REAL project directory (recovered from the project's session-transcript `cwd`, not the lossy slug), the real `memory_dir`, and an `item_count` of `.md` files excluding `MEMORY.md` (or `1` for a store whose only content is an inline `MEMORY.md`) — read-only, deriving everything from disk and emitting no audit event. An agent with no `projects/` directory returns an empty list.

## Requirements

### Functional Requirements

**Identity and location**

- **FR-001**: The `claude_code` type's standard config directory MUST be `~/.claude/`, which is the value `config_dir` defaults to under agent-registry FR-002. The presence of that directory MUST be the install marker agent-registry FR-004's discovery scans for, and agent-registry FR-008's one-agent-per-config-directory rule follows from it: Claude Code is registrable once unless the user overrides the path.

**Config files**

- **FR-002**: The curated allowlist (agent-registry FR-009) for `claude_code` MUST be exactly: `settings.json`, `settings.local.json`, `~/.claude.json` (which lives beside the config directory, not inside it), `CLAUDE.md` under the key `instructions`, and the `agents/` directory entry of FR-003. `CLAUDE.md` is human-authored instructions and its key says so; the agent's own written memory is FR-013's scan and spec memory's domain, not this file.
- **FR-003**: `agents/` MUST be the type's directory entry (agent-registry FR-027): one Markdown file per personal subagent, nested paths allowed, each child addressed and validated per agent-registry FR-028.

**Coffer MCP install**

- **FR-004**: The `McpInjectionSpec` agent-registry FR-015 installs through MUST write `mcpServers.coffer` in `~/.claude.json`, a command-map entry whose `command` is the resolved absolute shim path and whose `args` carry `--agent <name>`. Because the whole JSON document is reserialized on write, the `.bak` of agent-registry FR-013 is what makes that diff recoverable.

**Agent MCP entries**

- **FR-005**: The entries agent-registry FR-019 lists MUST be parsed from BOTH `~/.claude.json` `mcpServers` and `settings.json` `mcpServers`, each entry labelled with the file it came from. The format carries no per-entry enabled flag, so `enabled` is not reported for this type and there is nothing for Coffer to toggle.
- **FR-006**: A name present in both source files MUST be listed twice, once per file. A remove (agent-registry FR-020) or adopt (agent-registry FR-021) request MUST therefore carry the source file; a request that does not, for a name carried by both, is rejected as ambiguous rather than guessing which file to edit.

**Plugins**

- **FR-007**: The inventory agent-registry FR-024 lists MUST be derived from `<config_dir>/plugins/installed_plugins.json` and `known_marketplaces.json` — read, never written — with each plugin's enabled state read from the `enabledPlugins` map in `settings.json`, and `cache_present` from the install path the inventory records.
- **FR-008**: The toggle of agent-registry FR-025 MUST write only the `enabledPlugins` map in `settings.json`. `installed_plugins.json` and `known_marketplaces.json` MUST be byte-identical before and after.
- **FR-009**: The uninstall strategy of agent-registry FR-026 for this type MUST be delegation: Coffer runs `claude plugin uninstall <id>` and never hand-writes Claude's internal inventory, because the CLI owns that state. When the `claude` CLI is not on `PATH` the listing reports `can_uninstall=false` and the operation is `PLUGIN_UNINSTALL_UNSUPPORTED` (422); a CLI that runs and fails surfaces as `PLUGIN_UNINSTALL_FAILED` (422).

**The model catalogue**

- **FR-010**: The first catalogue source of agent-registry FR-033 for this type MUST be the CLI's own embedded **alias table**. The ids are the aliases the CLI itself accepts, and each label is the display name of the model that alias resolves to on a first-party account, so a release that moves an alias relabels the picker on its own. Both halves come from one embedded blob, located structurally; an anchor that stops matching MUST cost this source entirely rather than falling back to anything Coffer wrote down. The reason is entitlement: the versioned catalog is cumulative and account-blind, nothing on the machine says which of its models a given account may run, and the CLI's own picker offers the aliases and resolves each against the account at turn time.
- **FR-011**: The native-config source of agent-registry FR-035 for this type MUST be `additionalModelOptionsCache` in `~/.claude.json`, which contributes the account's own extra options. It MUST be read only. It is Claude Code's own CACHE of a field from its API response, so anything Coffer wrote into it would be clobbered; for this type the Coffer-side surfaces stay the only places a model is chosen, because Claude Code has no catalogue file Coffer may own.

**Reasoning effort levels**

- **FR-012**: The runtime source of agent-registry FR-037 for this type MUST be the installed Claude Agent SDK's own `EffortLevel` alias, read once and applied to every catalogue entry — the levels are a property of the runtime, not of a model, and `ClaudeAgentOptions.effort` renders as the CLI's own effort flag. An SDK that declares none yields an empty tuple and the controls hide themselves. No default level MAY be reported (agent-registry FR-038): `ClaudeAgentOptions.effort` defaults to `None`, meaning "whatever the CLI decides", and the CLI does not say what that is.

**Native memory**

- **FR-013**: The native-memory layout of agent-registry FR-039 for this type MUST be per project at `<config_dir>/projects/<slug>/memory/` — one row per project that has a `memory/` directory. The `project` label and `path` MUST be the REAL project directory, recovered from that project's session-transcript `cwd`; the slug encoding is lossy (`/`, `.` and `_` all collapse to `-`), so decoding the slug is a last-resort fallback and never the preferred source.
- **FR-014**: `item_count` for a store MUST be the number of `.md` fact files excluding `MEMORY.md` — or `1` when there are no fact files but `MEMORY.md` itself holds inline content, which is an older or hand-written hub document and is still one item of memory.

**Transcripts**

- **FR-015**: The transcript location of agent-registry FR-040 for this type MUST be `<config_dir>/projects/**/*.jsonl`. That directory is also the parent of this type's memory stores, which is why the store read of agent-registry FR-043 MUST accept only a directory the FR-013 layout would have listed and reject a sibling path under `projects/` that merely looks like one.

### Key Entities

- **`claude_code` descriptor**: The `AGENT_DESCRIPTORS` record this spec reads — default config dir `~/.claude/`, the FR-002 allowlist, the FR-004 injection spec, a `PluginCapability` whose uninstall strategy is the CLI delegation of FR-009, the FR-013 native-memory layout, the FR-015 transcript location, and the FR-010/FR-011 catalogue sources.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Every Acceptance Scenario in this spec is covered by at least one test marked `acceptance(spec="agent-registry/claude-code", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.
- **SC-002**: A plugin listing and a plugin toggle leave `installed_plugins.json` and `known_marketplaces.json` byte-identical, verified by a test that hashes them either side of both operations.
- **SC-003**: With the embedded alias table unreachable, the catalogue still answers from `additionalModelOptionsCache` and the request succeeds — the failure costs entries, never the response.

## Assumptions

- `~/.claude.json` sits beside the config directory rather than inside it, and only its `mcpServers` map is a write target; the rest of that file is the agent's own state, read where needed and never written.
- In practice, verified on a real machine, user-scope MCP servers live in `~/.claude.json` `mcpServers` and may also appear in `settings.json` `mcpServers`, which is why FR-005 parses both.
- The Claude Agent SDK that FR-012 reads is the one installed alongside the daemon; an environment without it reports no effort levels rather than guessing any.
- Everything the parent spec assumes applies here unchanged; this spec restates none of it.
