## 1. Backend

- [x] 1.1 `application/agent/connection_service.py`: `AgentConnectionService` over `ConnectionPart`s, the gateway entry (`McpConnectionPart`) first; status / connect / disconnect / connected_agents
- [x] 1.2 `surfaces/http/agent_connection_wiring.py`: the memory hook as a `ConnectionPart` gated on the `memory` feature; composed in `app.py`
- [x] 1.3 `GET` / `POST` / `DELETE /api/v1/agents/{uid}/coffer-connection`; `/mcp-install` and `/memory/delivery*` removed
- [x] 1.4 CLI `coffer agent connect | disconnect | connection`; `coffer agent mcp status|install|uninstall` and `coffer memory delivery*` removed
- [x] 1.5 `delivery_switch`: switching `memory` on installs into connected agents; the `memory_delivery_withdrawn` list and its helpers removed
- [x] 1.6 Contracts (agent-registry, memory), data models, frontend codegen

## 2. Frontend

- [x] 2.1 `AgentConnectionControls` (header button with a help tooltip, table badge), bulk Connect / Disconnect
- [x] 2.2 Memory tab's Delivery card and the memory delivery API/hooks removed; gateway rows read the connection's `mcp` part
- [x] 2.3 en/zh strings: `agents.cofferConnection.*` added, `agents.mcp.*`, `agents.bulkInstallMcp`, `memory.delivery.*` removed

## 3. Tests and docs

- [x] 3.1 Acceptance-marked tests for every new scenario; existing tests moved to the connection routes
- [x] 3.2 Guides (agents, memory, connect-a-client, quickstart, install, experimental-features, faq, knowledge, troubleshooting, chat), reference (CLI, REST, configuration, filesystem), architecture (memory, daemon, chat), README, the `coffer-guide` skill text
