# Agent Mechanisms Are Optional Facets on the Descriptor, and Projection Is One Registry

**Status**: Accepted
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [Per-Agent Behaviour Lives in One Descriptor Record per Agent](agent-descriptor-manifest.md), [LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md), [Coffer Drives Claude Code Through the Agent SDK and Codex Through `codex app-server`](driving-agents-through-sdk-and-app-server.md), [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), [Skills Reach an Agent as a Directory Link to One Master Folder](cross-platform-skill-delivery.md), [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database](one-level-triggered-reconciler-compares-parameters.md), research note [agent plugins](../research/agent-plugins.md), research note [agent chat clients](../research/agent-chat-clients.md), spec agent-registry "Support exactly the Claude Code and Codex agent types", spec chat "Run Claude Code and Codex as subprocess providers on the type's one agent", spec provider-switching "Keep projection transforms pure", PR #87, PR #309

## Context

[Per-Agent Behaviour Lives in One Descriptor Record per Agent](agent-descriptor-manifest.md)
puts every per-agent *value* — config directory, allowlist, MCP file shape,
skill subpath, plugin capability — in `AgentDescriptor`
(`domain/agent/descriptor.py`). That leaves the per-agent *mechanisms*: the
code that translates, runs or reads. Before this decision they branched on
`AgentType` in their own modules:

- **Provider projection** was keyed by wire protocol, with a table that
  assumed **exactly one agent type per protocol and one protocol per agent
  type**; deactivation, the boot heal and a `use-builtin/{wire}` route all
  relied on it. A second agent that speaks the Anthropic protocol had no
  representation.
- **Native memory and transcripts** branched on the agent type in the domain
  and in the readers under `infrastructure/memory/readers/` and
  `infrastructure/agent/`.
- **Chat drivers** were constructed by name in the chat wiring.
- **Model catalogue** probes (`infrastructure/agent/claude_binary_models.py`,
  `infrastructure/agent/codex_rpc_models.py`) were selected by type.

Adding a third agent meant finding each of those by search, the failure
mode the descriptor ADR's Option A lost for. And the set of things Coffer
places into an agent grows past MCP, skills and providers (rules,
commands, subagents, permissions), each of which lands in a different file
per agent, at user level, project level, or in a directory several agents
share.

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

| Facet | Answers | Code it absorbs |
| --- | --- | --- |
| `projection` | Which asset types this agent can receive, where each lands, and how Coffer's asset is translated into the agent's native shape | the MCP injection spec, the skill subpath, the provider translation (`domain/provider/agent_projection.py`) |
| `driver` | How Coffer runs a turn on this agent | the Claude Code and Codex chat drivers (`infrastructure/chat/drivers.py`) |
| `memory_reader` | How the agent's native memory is read, so what the agent learned can enter the memory hub ([Sync Memory Into Each Agent's Own Memory](sync-memory-into-each-agents-own-memory.md)) | `domain/agent/native_memory.py`, `domain/agent/codex_memory.py`, `infrastructure/memory/readers/` |
| `dependency_probe` | Whether the agent is installed here, which version, and what that version supports (model catalogue) | the program probe (`infrastructure/agent/program_probe.py`), the model catalogue probes |

The projection facet is a **registry keyed by asset type × landing point**.
Each entry states:

- the landing point: **user** (the agent's config directory), **project**
  (inside a repository), or **shared** (a directory more than one agent
  reads — the reconciler writes it once and counts it for each reader);
- the translation: a pure function from Coffer's asset to the native
  fragment, as spec provider-switching "Keep projection transforms pure"
  already requires for providers;
- a capability declaration: only the fields the two shipped agents actually
  use (for providers, the protocols the agent accepts, which may be none).

Provider projection is not keyed by protocol: an agent declares which
protocols it accepts, a connection reaches agents by scope, and deactivation
names an **agent**, not a wire (`POST /providers/use-builtin/{agent_type}`).
The one projection mode is pointing the agent at Coffer's local model proxy;
the facet has no second mode.

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
  one-protocol-one-agent assumption has no representation left.
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

The design this replaced.

- **Pros.** No new abstraction; each module reads top to bottom.
- **Cons.** Every new agent or asset type is a search across the modules
  above; the Protocol to AgentType bijection stays implicit in several places;
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

The facets are bound in `surfaces/http/agent_facet_wiring.py`, which calls
`bind_facets` in `domain/agent/facets.py`; each implementation declares the
agent type it serves and the binder groups them onto a copy of the table.
Consumers receive the resulting `AgentCatalog` and ask it for a facet.

Rules a future change must respect:

- Outside `domain/agent/`, `infrastructure/agent/` and the facet
  implementations, no code branches on `AgentType`;
  `scripts/check_agent_type_branches.py` fails the build on it.
- A capability field is added only when a shipped agent uses it.
- A shared landing point is written once and never removed while any reader
  still wants it.

## Consequences

- The descriptor ADR's list of mechanisms that branch on `AgentType` is this
  ADR's facet table; [Per-Agent Behaviour Lives in One Descriptor Record per Agent](agent-descriptor-manifest.md)
  holds the values, this one the mechanisms.
  [LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md)
  has the provider translation as one entry of the registry.
- The projection registry is the target list of
  [One Level-Triggered Reconciler](one-level-triggered-reconciler-compares-parameters.md):
  each entry supplies `desired`, `observe` and `apply` for its asset type.
- Provider projection has one mode: the agent is pointed at the local model
  proxy. A mode that writes the vendor endpoint into the agent's config is not
  part of the facet.
- Not built yet: the `project` and `shared` landing points. `Landing`
  declares them, but every entry the two shipped agents have lands at `user`.
- Not built yet: ACP drivers. The two shipped agents are driven directly; an
  ACP driver would be added with the first long-tail agent that needs it.
- Not built yet: one facet contract test run against a fake agent directory
  for each shipped agent; `backend/tests/unit/domain/agent/test_facets.py`
  covers binding and the registry, not each facet's behaviour.
