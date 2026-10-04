## Why

Per-agent *values* already live in one descriptor record per agent, but the
per-agent *mechanisms* — how a connection is written into an agent, how its
memory hook is installed, how its memory is read, how a turn is driven, how it
is detected — still branched on the agent type in their own modules, and three
places still assumed that one wire protocol stands for exactly one agent. The
ADR [Agent Mechanisms Are Optional Facets on the Descriptor](../../../docs/decisions/agent-mechanisms-are-optional-facets-on-the-descriptor.md)
decides to put those mechanisms behind optional facets named by the descriptor.

Detection was one weak signal — a config directory that survives an
uninstall — and nothing showed the hooks an agent will actually run.

## What Changes

- Four optional facets on each agent descriptor — projection (a registry of
  asset type x landing point with a translation and a minimal capability
  declaration: MCP entry, skills directory, provider projection, delivery
  hook), driver, memory reader, dependency probe — bound to their
  implementations at the composition root.
- Provider protocols are declared per agent (possibly none); nothing maps a
  protocol to one agent. `POST /api/v1/providers/use-builtin/{agent_type}`
  replaces `use-builtin/{wire}`, and `coffer provider builtin <agent_type>`
  replaces the wire argument. The legacy wire-keyed key route resolves through
  the agents that declare the wire.
- Detection has two signals: the agent's program on its real `PATH` (with its
  version) and its config directory, named `installed_active`,
  `installed_never_run`, `config_only` (and `missing` for a registered agent
  whose program and directory are both gone). Candidates carry state and
  version and include the directory `CLAUDE_CONFIG_DIR` / `CODEX_HOME` names
  in the daemon's environment; only an `installed_active` candidate is added.
  The agent read model carries `state` and `version`.
- `GET /api/v1/agents/{uid}/hooks`, `coffer agent hooks <name>` and an agent
  Hooks tab list every hook in the agent's native config read-only, mark
  Coffer's own and report its health (current, stale, missing) and last fire.
- A build gate fails on code outside the descriptor and its facets that names
  an agent type.
