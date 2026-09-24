# Per-Agent Behaviour Lives in One Descriptor Record per Agent

**Status**: Accepted
**Date**: 2026-06-14
**Deciders**: Yuxing Wu
**Related**: [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), [Kind Plugin Contract](kind-plugin-contract.md), [Cross-Platform Skill Delivery](cross-platform-skill-delivery.md), [Stdio Shim Bridge](stdio-shim-bridge.md), [Provider Connections Projected Into Agent Config](provider-connections-projected-into-agent-config.md), [Model Catalogue Read From the Agent](model-catalogue-read-from-the-agent.md), [Driving Agents Through the SDK and App Server](driving-agents-through-sdk-and-app-server.md), [SQLite and Alembic Persistence](sqlite-alembic-persistence.md), spec agent-registry "Support exactly the Claude Code and Codex agent types", spec agent-registry "Define a curated config-file allowlist per type", spec agent-registry "Install Coffer's MCP server into an agent in one action", spec agent-registry "Uninstall a plugin by the type's own strategy", PR #87, PR #309

## Context

Coffer manages agent products it does not own. For each one it has to know
where the config directory is, which environment variable moves it, which files
in it Coffer may show and edit, which file holds MCP servers and in what shape,
where skills are delivered, and whether and how plugins can be toggled or
uninstalled.

Before PR #87 (2026-06-14) those answers were `if agent_type == ...` branches
spread across `types.py`, the config-file allowlist, the MCP install service and
auto-detect. PR #87 added four agents at once (Cursor, OpenCode, OpenClaw,
Hermes), which would have meant touching every one of those sites four times
over. The answers are static facts about a product, not behaviour that varies at
runtime, so the question was where to keep them.

The agent set has since moved twice. The four extra types were cut in 2026-06
(migration `0031`), brought back, and cut again in 2026-09 by PR #309 (migration
`0048`). `AgentType` is now exactly `claude_code` and `codex`.

## Options Considered

### Option A — Branch on `AgentType` at each use site

Every consumer asks "which agent is this?" and switches.

Pros: no indirection; each site reads top to bottom. Cons: adding or removing an
agent is a search across the codebase, and a missed branch fails only when that
agent reaches that path; nothing lists what an agent needs in one place, so a
reviewer cannot see that Codex's MCP file is TOML while Claude Code's is JSON
without opening two services. It lost when PR #87 would have had to repeat
every branch four more times.

### Option B — One frozen descriptor record per agent in a domain table (chosen)

`backend/coffer/domain/agent/descriptor.py` defines a frozen `AgentDescriptor`
dataclass and `AGENT_DESCRIPTORS: dict[AgentType, AgentDescriptor]`, looked up
through `descriptor_for()`. A record carries:

- identity — `type`, `display_name`;
- location — `config_subpath` (`.claude`, `.codex`, resolved against the live
  `$HOME`), `home_env_var` (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`), which every
  process Coffer spawns for a custom config directory carries
  (`domain/agent/home_env.py`);
- the config-file allowlist — `config_files`, a builder that takes the agent's
  effective config directory and returns its `ConfigFileSpec` tuple (the
  builders live in `domain/agent/allowlists.py`);
- MCP — `mcp: McpInjectionSpec` (which allowlist key holds the entry, the
  container key `mcpServers` or `mcp_servers`, JSON or TOML, entry style) and
  `mcp_source_keys`, the files scanned for the agent's own MCP entries
  (Claude Code reads `global` and `settings`; Codex reads `config`);
- skills — `skill_subpath` under the config directory;
- plugins — `plugins: PluginCapability` (model, which file holds the toggle,
  whether toggle and uninstall are offered, and the uninstall strategy: Claude
  Code's is delegated to `claude plugin uninstall`, because its install
  inventory is an internal file Coffer never writes).

`AgentType` keeps only the persisted identity and delegates its
`display_name`, `config_dir()`, `default_skill_dir()` and `detect_marker()` to
the table. `types.py` and `config_files.py` import the descriptor module lazily,
inside the functions that need it, so the descriptor module can import their
primitives (`AgentType`, `ConfigFileSpec`) at top level without an import cycle.

Pros: adding or removing an agent is one record plus its allowlist builder, and
the record is a readable inventory of what Coffer touches in that product; the
record is pure data in the domain layer, so it is unit-testable and needs no
filesystem; a facet a product lacks is `None` (`mcp=None`, `plugins=None`) and
the consumers already handle that case. Cons: the lazy imports are a wart that
a reader has to be told about; a descriptor can only describe differences the
dataclass already has a field for, so a genuinely new mechanism still needs
code. It wins because the per-agent answers Coffer needs for config, MCP, skills
and plugins really are static data, and a table is the cheapest correct home
for static data.

### Option C — A class per agent with overridden methods

A `ClaudeCodeAgent` and a `CodexAgent`, each subclassing an abstract base and
overriding `install_mcp()`, `list_plugins()` and so on.

Pros: behaviour and data sit together; a new mechanism is a new method. Cons:
most of what differs is a value (a path, a key, a format), and a class
hierarchy turns each value into a method a reader has to open; the base class
grows a method per facet, and every subclass must implement or inherit each
one, so a facet one product lacks becomes a stub. It lost because the
differences are overwhelmingly data, and the few that are mechanisms (JSON
versus TOML, CLI versus file-edit uninstall) are already expressed as enums the
shared code switches on once.

### Option D — A user-editable manifest file

Ship the descriptors as YAML or JSON the user can extend, so a new agent could
be added without a release.

Pros: support for another agent without waiting for Coffer. Cons: a descriptor
names files Coffer will write into and the environment it spawns processes
with, so a wrong entry is a write into the wrong file; a new agent also needs
code Coffer does not have (its transcript format, its chat driver, its model
catalogue source), so a data-only extension point would promise support it
cannot deliver. It lost on both counts.

### Option E — Keep an `enabled` flag on each record

The descriptor carried `enabled`, meant to hide a type from auto-detect while
it was unfinished.

Pros: an agent could be half-landed without being offered. Cons: it was `True`
on every record it ever held, and registration accepted any manifest type
anyway, so its only reachable effect would have been hiding an agent from the
one screen that helps a user add it. It was removed; withdrawing an agent means
removing it from `AgentType` and the table, which is what migrations `0031` and
`0048` did.

## Decision

Keep one frozen `AgentDescriptor` record per supported agent in
`AGENT_DESCRIPTORS`, and route every per-agent answer about location, config
files, MCP injection, skill delivery and plugins through `descriptor_for()`.
`AgentType` is the persisted identity and nothing more. There are exactly two
records, `claude_code` and `codex`. The table is code, not user data.

## Consequences

- Adding an agent is a new `AgentType` member, a descriptor record, an allowlist
  builder, and the product-specific code for the facets the table does not
  describe. Removing one is the reverse plus a data migration, because
  `AgentConfig.model_validate` raises on a stored row whose type left the enum;
  `0048` deletes those rows and leaves files Coffer wrote into the removed
  agents' directories alone; the daemon names them in its log once at startup
  (`surfaces/http/removed_agent_notice.py`).
- The table covers configuration, MCP, skills and plugins. Other per-agent
  behaviour still branches on `AgentType` in its own module, because it is a
  mechanism rather than a value: provider projection
  (`domain/provider/projection.py`), transcript and native-memory readers
  (`domain/agent/transcripts.py`, `domain/agent/native_memory.py`), the Codex
  `model/list` RPC (`infrastructure/agent/codex_rpc_models.py`), memory delivery
  hooks (`application/memory/delivery.py`) and the chat drivers. A new agent has
  to be threaded through those too; the table does not list them.
- The allowlist builder is the security boundary for config-file access, so a
  new record's builder decides exactly which files Coffer can read and write in
  that product (see [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md)).
  Codex's credential file, for example, is absent from its builder and so
  unreachable.
- Tests that override `$HOME` see consistent paths everywhere, because every
  location is resolved from the live home at call time rather than captured at
  import.
