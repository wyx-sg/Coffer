## Why

Coffer writes more than one thing into an agent's own configuration — the gateway MCP entry, and (while `memory` is on) the memory delivery hook — but each had its own button in a different place: **Install Coffer MCP** in the agent page header and on the Agents list, and a separate **Delivery** card on the agent's Memory tab. A person who wanted the agent to "use Coffer" had to know that there were two, and where each lived; one without the other is an agent that is half hooked up and says nothing about it.

## What Changes

- One act, **Connect to Coffer** / **Disconnect from Coffer** (「接入 Coffer」/「断开 Coffer」), installs or removes every part Coffer writes into an agent that applies to it now: the gateway MCP entry always, the memory delivery hook while the `memory` feature is on.
- The connection is reported part by part with a state: **Connected**, **Not connected**, or **Needs repair** when only some parts are in place (connecting again puts the rest back).
- REST: `GET` / `POST` / `DELETE /api/v1/agents/{uid}/coffer-connection` replace `/api/v1/agents/{uid}/mcp-install` and the `/api/v1/memory/delivery*` routes, which are removed.
- CLI: `coffer agent connection <name> [--json]`, `coffer agent connect <name>`, `coffer agent disconnect <name>` replace `coffer agent mcp status|install|uninstall` and `coffer memory delivery|delivery-install|delivery-remove`, which are removed.
- Web: the agent page header's button and the Agents list's column and bulk actions become Connect / Disconnect with the connection state; the Memory tab's Delivery card is removed. Which parts a connect installs is behind a help tooltip.
- Switching `memory` on installs the hook into every **connected** agent (one carrying the gateway entry). The `memory_delivery_withdrawn` list in `daemon-config.json`, which remembered where to put the hook back, is gone: the connection is that record now. Switching `memory` off still removes the hook everywhere.
- Every part keeps its own audit events (`agent_mcp_installed` / `agent_mcp_uninstalled`, `memory_delivery_installed` / `memory_delivery_removed`).

## Capabilities

### New Capabilities

### Modified Capabilities
- `agent-registry`: adds "Connect an agent to Coffer in one action", "Report an agent's Coffer connection part by part", "Disconnect an agent from Coffer" and "Show the Coffer connection on the agent pages"; the MCP install/uninstall/status requirements now describe the connection's `mcp` part; the surface roster and the audit requirement follow.
- `memory`: the hook is installed by connecting the agent; "Show delivery state on the agent's own page" is removed; the REST/CLI family no longer manages delivery.
- `experimental-features`: switching `memory` on installs the hook into every connected agent.

## Impact

- Backend: new `application/agent/connection_service.py`, `surfaces/http/agent_connection_routes.py`, `surfaces/http/agent_connection_wiring.py`, `surfaces/cli/agent_connection_cmd.py`; `application/memory/delivery_switch.py` rewritten around connected agents; removed `surfaces/cli/memory_delivery_cmd.py`, the delivery routes and schemas, the `/mcp-install` routes, and the withdrawn-list helpers in `infrastructure/daemon/config.py` / `feature_settings.py`.
- Contracts: agent-registry (`/coffer-connection`, `CofferConnection`, `CofferConnectionPart`), memory (delivery paths and schemas removed); frontend codegen.
- Frontend: `AgentMcpControls` → `AgentConnectionControls`, `AgentBulkActions`, `AgentTable` column, `AgentMemoryDelivery` removed, en/zh strings.
- Docs: guides (agents, memory, connect-a-client, quickstart, install, experimental-features, faq, knowledge, troubleshooting), reference (CLI, REST, configuration, filesystem), architecture (memory, daemon, chat), README.
- An existing `memory_delivery_withdrawn` key in `daemon-config.json` is no longer read; an agent that had only the gateway entry reads as **Needs repair** while `memory` is on until it is connected again.
