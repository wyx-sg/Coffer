# Agent Mechanisms Are Optional Facets on the Descriptor, and Projection Is One Registry

**Status**: Proposed
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [Per-Agent Behaviour Lives in One Descriptor Record per Agent](agent-descriptor-manifest.md), [LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md), [Coffer Drives Claude Code Through the Agent SDK and Codex Through `codex app-server`](driving-agents-through-sdk-and-app-server.md), [Aggregate the Agents' Memory; Never Write It](aggregate-agent-memory-never-write-it.md), [Coffer's Agent Hooks Are Marker-Scoped, Explicit, Audited and Repaired When Stale](agent-hook-installation.md), [Skills Reach an Agent as a Directory Link to One Master Folder](cross-platform-skill-delivery.md), [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database](one-level-triggered-reconciler-compares-parameters.md), research note [agent plugins](../research/agent-plugins.md), research note [agent chat clients](../research/agent-chat-clients.md), spec agent-registry "Support exactly the Claude Code and Codex agent types", spec chat "Ship Claude Code and Codex subprocess providers on the type's one agent", spec provider-switching "Keep projection transforms pure", PR #87, PR #309

## Context

[Per-Agent Behaviour Lives in One Descriptor Record per Agent](agent-descriptor-manifest.md)
put every per-agent *value* — config directory, allowlist, MCP file shape,
skill subpath, plugin capability — in `AgentDescriptor`
(`domain/agent/descriptor.py`). Its Consequences section is explicit that
*mechanisms* were left out and still branch on `AgentType` in their own
modules. They still do:

- **Provider projection** — `domain/provider/projection.py` holds
  `_TARGETS: dict[Protocol, ProjectionTarget]` (line 87) and
  `wire_for_agent` (line 104), and `application/provider/switch_ops.py` holds
  `AGENT_FOR_WIRE: dict[Protocol, AgentType]` (line 34), which
  `deactivate(wire)` and `ProviderService` use to find "the" agent behind a
  wire. The *writer* is already chosen per agent type (`_AGENT_TARGETS`,
  line 96, after the provider ADR's Option E was retired), but deactivation,
  the boot heal (`application/provider/boot_reconcile.py` calls
  `wire_for_agent`) and the back-compat `use-builtin/{wire}` route still
  assume **exactly one agent type per protocol and one protocol per agent
  type**. A second agent that speaks the Anthropic protocol has no
  representation.
- **Memory delivery** — `application/memory/delivery.py` `_ADAPTERS:
  dict[AgentType, DeliveryAdapter]`.
- **Native memory and transcripts** — `domain/agent/native_memory.py`
  (`if agent_type is AgentType.CLAUDE_CODE … CODEX`),
  `domain/agent/transcripts.py` (a dict keyed by `AgentType` value), and the
  readers under `infrastructure/memory/readers/` and `infrastructure/agent/`.
- **Chat drivers** — `surfaces/http/chat_provider_wiring.py` constructs
  `ClaudeSdkProvider` and `CodexAppServerProvider` by name.
- **Model catalogue** — `infrastructure/agent/claude_binary_models.py` and
  `infrastructure/agent/codex_rpc_models.py`, selected by type.

Adding a third agent today means finding each of those by search, the failure
mode the descriptor ADR's Option A lost for. And the set of things Coffer
places into an agent is about to grow past MCP, skills, providers and hooks
(rules, commands, subagents, permissions), each of which lands in a
different file per agent, at user level, project level, or in a directory
several agents share.

One candidate landing format was measured on 2026-09-29 in isolated config
directories, Claude Code 2.1.281 and Codex 0.155.1: the **agent plugin**.
Claude Code loads a plugin in place from `~/.claude/skills/<x>/.claude-plugin/plugin.json`
as `<x>@skills-dir`, and a `SessionStart` hook in it fires without an
install step; but its skills are renamed `plugin:skill` and its MCP tools
`mcp__plugin_<plugin>_<server>__<tool>`. Codex copies a plugin into
`plugins/cache/<marketplace>/<plugin>/local/` at install time, so a skill added
to the source afterwards is invisible until reinstall, and its skills are
renamed `plugin:skill` too. Renaming breaks
[Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md),
and install-time copying defeats the one-master-folder delivery.

## Options Considered

### Option A — Mechanism facets on the existing descriptor, projection as a registry (chosen)

`AgentDescriptor` gains four optional **ports**, each `None` where the agent
lacks the mechanism, each implemented in `infrastructure/` and bound to the
record at the composition root (the domain record names the port type, never
the implementation):

| Facet | Answers | Today's code it absorbs |
| --- | --- | --- |
| `projection` | Which asset types this agent can receive, where each lands, and how Coffer's asset is translated into the agent's native shape | `mcp_install`, skill subpath, `domain/provider/projection.py`, `_ADAPTERS` in `memory/delivery.py` |
| `driver` | How Coffer runs a turn on this agent | `ClaudeSdkProvider`, `CodexAppServerProvider` |
| `memory_reader` | How the agent's native memory and transcripts are read (read only, per [Aggregate the Agents' Memory; Never Write It](aggregate-agent-memory-never-write-it.md)) | `native_memory.py`, `transcripts.py`, the readers |
| `dependency_probe` | Whether the agent is installed here, which version, and what that version supports (model catalogue, hook events) | `detect_marker`, `claude_binary_models.py`, `codex_rpc_models.py` |

The projection facet is a **registry keyed by asset type × landing point**.
Each entry states:

- the landing point: **user** (the agent's config directory), **project**
  (inside a repository), or **shared** (a directory more than one agent
  reads — the reconciler writes it once and counts it for each reader);
- the translation: a pure function from Coffer's asset to the native
  fragment, as spec provider-switching "Keep projection transforms pure"
  already requires for providers;
- a capability declaration: only the fields the two shipped agents actually
  use (for providers, the protocols the agent accepts, which may be none; for
  hooks, the events it offers).

Provider projection stops being keyed by protocol: an agent declares which
protocols it accepts, a connection reaches agents by scope, and deactivation
names an **agent**, not a wire. `AGENT_FOR_WIRE`, `_TARGETS` and
`wire_for_agent` go; the `use-builtin/{wire}` route is migrated to take an
agent.

The **driver** facet is direct-first: Claude Code through the Agent SDK and
Codex through `codex app-server`, as
[Coffer Drives Claude Code Through the Agent SDK and Codex Through `codex app-server`](driving-agents-through-sdk-and-app-server.md)
decided. A generic ACP driver is added only for a long-tail agent that
speaks ACP natively (the research note lists Gemini CLI, OpenCode, Cline,
Kimi CLI and Qwen Code); it never replaces a direct driver.

- **Pros.** A new agent is one record plus the facet implementations it has;
  a missing facet is `None` and every consumer already handles absence. The
  projection registry is exactly the list of targets the reconciler
  iterates, so a new asset type is a registry entry, not a new service. The
  one-protocol-one-agent assumption is removed at its three remaining sites.
  Facets can be contract-tested once against a fake agent directory.
- **Cons.** The descriptor now references ports whose implementations live in
  `infrastructure/`, so binding moves to the composition root and the record
  is no longer pure data. Four port interfaces are a contract to review. The
  capability declaration must be kept deliberately small or it becomes
  speculative design for agents Coffer does not support.
- **Why it wins.** It finishes the descriptor ADR along the line it already
  drew — values in the record, mechanisms named by the record — and gives
  the reconciler one place to find every target.

### Option B — Keep branching on `AgentType` in each mechanism module

The status quo for mechanisms.

- **Pros.** No new abstraction; each module reads top to bottom.
- **Cons.** Every new agent or asset type is a search across the modules
  above; the Protocol ↔ AgentType bijection stays implicit in three places;
  nothing lists what an agent can receive, so neither the reconciler nor the
  UI can ask. It is the option the descriptor ADR already rejected for
  values.
- **Why it loses.** The number of mechanisms is growing, not shrinking.

### Option C — A class per agent implementing every mechanism

`ClaudeCodeAgent` / `CodexAgent` subclassing an abstract base with
`project_mcp`, `run_turn`, `read_memory`, …

- **Pros.** Behaviour sits together; a mechanism is a method.
- **Cons.** The descriptor ADR's Option C objection holds: the base class
  grows a method per asset type and a stub wherever an agent lacks one, and
  the values already in the descriptor would be split across two homes. A
  projection registry expresses "this agent has no project-level landing for
  rules" as a missing entry rather than a method that raises.
- **Why it loses.** Optional, independently present mechanisms fit
  composition better than inheritance.

### Option D — The agent plugin as the universal projection target

Package everything Coffer delivers as one plugin per agent, and let the
agent's own plugin loader place it.

- **Pros.** One artefact per agent; the vendors' own format; hooks, skills
  and MCP servers in one bundle.
- **Cons.** Measured above: both agents rename skills to `plugin:skill`,
  Claude Code renames MCP tools, and Codex copies at install so later edits
  do not arrive. Each of those breaks a standing decision (fixed names, one
  master folder, reach applied by the reconciler).
- **Why it loses.** The evidence. Plugins remain something Coffer *reads and
  toggles* (the descriptor's `plugins` capability), not a place it writes to.
  The single open use — a hook-only plugin in Claude Code's skills directory —
  can be revisited as a projection entry if the hook file becomes unworkable.

### Option E — ACP as the one driver for every agent

Drive every agent through the Agent Client Protocol, using adapters such as
`claude-agent-acp` and `codex-acp` for the two shipped agents.

- **Pros.** One driver implementation; every ACP agent becomes reachable.
- **Cons.** For Claude Code and Codex, ACP is a layer over the same SDK and
  app-server Coffer already drives (the research note records `codex-acp`
  starting app-server and translating), so it adds a process and a
  translation while hiding vendor features the direct protocols expose.
  One adapter's registry licence and its GitHub licence disagree.
- **Why it loses.** Direct is strictly better where it exists; ACP earns its
  place only where it is the agent's own protocol.

## Decision

Agent-specific **mechanisms** are four optional facets of the existing
`AgentDescriptor` — `projection`, `driver`, `memory_reader`,
`dependency_probe` — named by the record in `domain/` and bound to
implementations at the composition root. `projection` is a registry of
asset type × landing point (user, project, shared), each with a pure
translation and a minimal capability declaration. Provider protocols are
declared per agent and may be empty; nothing maps one protocol to one agent
type. Drivers are direct where the vendor offers a structured protocol; ACP
serves only agents that speak it natively. The agent plugin format is not a
projection target.

Rules a future change must respect:

- Outside `domain/agent/` and the facet implementations, no code branches on
  `AgentType`.
- A capability field is added only when a shipped agent uses it.
- A shared landing point is written once and never removed while any reader
  still wants it.

## Consequences

- **Extends** [Per-Agent Behaviour Lives in One Descriptor Record per Agent](agent-descriptor-manifest.md);
  its list of mechanisms that "still branch on `AgentType`" becomes this
  ADR's facet table, and that ADR is rewritten to point here when this one is
  accepted. [LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md)
  keeps its design; only the protocol-keyed lookups are removed.
- The projection registry is the target list of
  [One Level-Triggered Reconciler](one-level-triggered-reconciler-compares-parameters.md):
  each entry supplies `desired`, `observe` and `apply` for its asset type.
- Provider projection keeps a reserved second mode — pointing the agent at a
  local proxy instead of writing the endpoint — as a declared option of the
  facet, not implemented.
- **Follow-up work:** the four port interfaces and their bindings; moving
  the sites in Context behind them; deleting `AGENT_FOR_WIRE`, `_TARGETS` and
  `wire_for_agent` and migrating `use-builtin/{wire}`; a shared facet
  contract test run against a fake agent directory for each shipped agent; a
  grep gate that fails on `AgentType.` branches outside `domain/agent/` and
  the facet implementations.
