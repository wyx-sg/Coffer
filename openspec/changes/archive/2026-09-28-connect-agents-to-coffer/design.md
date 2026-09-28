## What a connection is made of

Everything Coffer writes into an agent's own configuration, one per-agent act each, was surveyed:

| Candidate | Written by | Per-agent act? | Part of the connection? |
| --- | --- | --- | --- |
| Gateway MCP entry (`coffer` in `.claude.json` / `config.toml`) | agent kind, `AgentMcpService` | yes — a button | **yes** (`mcp`), always |
| Memory delivery hook (`settings.json` / `hooks.json`) | memory kind, `DeliveryService` | yes — the Delivery card | **yes** (`memory_hook`), while `memory` is on |
| `coffer-guide` skill link in the agent's skills directory | skill kind, the delivery reconcile | no — a skill reaches an agent iff it is enabled and the agent is in its reach | no |
| Provider projection (model/provider settings) | provider kind | no — a provider switch, not a Coffer hook-up | no |
| Context-injection hooks | — | removed long ago | — |

The guide skill is delivered by the skill kind's own predicate (enabled + reach), with its own controls on the Skills pages. Folding it into the connection would give one resource two owners of its reach — the skill's reach control and an agent's connect button — which then disagree the first time either is used. It stays where it is; the connection is what Coffer writes into files that belong to the agent's own configuration.

Both agent types (Claude Code, Codex) support both parts today. A future type without a hook adapter simply has no `memory_hook` part.

## Shape

`application/agent/connection_service.py` owns the connection and knows its parts only through a `ConnectionPart` port (`key`, `supports(type)`, `enabled()`, `status` / `install` / `remove`). The `mcp` part wraps `AgentMcpService`. The `memory_hook` part wraps the memory kind's `DeliveryService` and is adapted at the composition root (`surfaces/http/agent_connection_wiring.py`), because the agent kind may not import the memory kind (import-linter's cross-kind fences). Each part keeps its atomic write, `.bak` and audit event; the service writes and audits nothing of its own, so one connect is recorded as the part installs it performed — the same events as before.

- **Connect** (re)installs every applicable part, the gateway entry first: its refusal (no shim) writes nothing, so a connect that cannot work fails before touching any file. Reinstalling an installed part is deliberate — it is how a stale shim path or hook command is brought current.
- **Disconnect** removes every part the type supports, *applicable or not*: a hook left behind while `memory` was off is still Coffer's to take out.
- **Status** lists only the applicable parts. `connected` = all installed, `disconnected` = none, `partial` = some. The UI calls `partial` "Needs repair" and offers Connect.

## Route and command names

`/api/v1/agents/{uid}/coffer-connection` (GET/POST/DELETE) replaces `/mcp-install` rather than broadening it: the old name would describe one part of what the route does. The memory kind's `/memory/delivery*` routes and `coffer memory delivery*` commands go too — a second way to install one part would let an agent be "connected" with a hook the connection did not put there, and there is no shim period (the CLI and the web UI ship with the daemon). CLI: `coffer agent connect | disconnect | connection`, at the top of the `agent` group because they are acts on the agent itself; `coffer agent mcp` keeps only the direct-entry commands.

UI words: 「接入 Coffer」/「断开 Coffer」, "Connect to Coffer" / "Disconnect from Coffer" — "install Coffer" would read as installing the app.

## The `memory` switch, without a withdrawn list

Before, switching `memory` off recorded the agents it took the hook out of (`memory_delivery_withdrawn` in `daemon-config.json`) and switching on put it back into exactly those. With a connection, the record already exists: an agent carrying the gateway entry is connected, and a connected agent is one that should have the hook while `memory` is on. So:

- switch **off**: remove the hook everywhere (unchanged);
- switch **on**: install the hook into every connected agent that lacks it, then repair stale commands;
- **boot**: off → remove everywhere; on → repair stale commands only.

Boot does not install into connected agents that lack the hook. Such an agent is either one that had only the gateway entry before this change, or one whose hook someone removed by hand; either way installing it at a restart would be a write nobody asked for. Its page says **Needs repair**, and connecting is the explicit act. The switch-on path does install, because switching a feature on while agents are connected *is* asking for the feature in them.

The old list also covered "off, restart, on": the switch-on path now derives its targets from the agents' own files, so there is nothing to remember across the restart. A disconnected agent is never given the hook by the switch, which the old list could not promise (disconnecting while `memory` was off would have left the uid on the list).
