## 1. Facets

- [x] 1.1 Facet slots on the descriptor; projection registry (asset type x landing), dependency probe port, bound catalogue and binder
- [x] 1.2 Provider projection facets (Claude Code, Codex) with plans and presence checks; projector and boot heal on the facet
- [x] 1.3 Delivery hook adapters, memory readers and drivers declare their agent and are bound at the composition root
- [x] 1.4 Remove `AGENT_FOR_WIRE`, `_TARGETS`, `wire_for_agent`; revert by agent type on REST and CLI; legacy key route by declared protocols
- [x] 1.5 Descriptor-driven MCP home migration

## 2. Detection

- [x] 2.1 Login-shell `PATH` in the platform package; program probe with version and cache
- [x] 2.2 Two-signal detection states on candidates (incl. environment-named directories) and on the agent read model
- [x] 2.3 `coffer scan` rows carry state and name the add command only for an addable candidate

## 3. Hooks

- [x] 3.1 Hook parsing and the read-only hooks service (user files, enabled plugins, Coffer's own with health and last fire)
- [x] 3.2 `GET /api/v1/agents/{uid}/hooks`, `coffer agent hooks`, Hooks tab

## 4. Gate, tests, docs

- [x] 4.1 `scripts/check_agent_type_branches.py` in `make lint`, listed in the harness doc
- [x] 4.2 Shared facet contract test per shipped agent; unit tests for registry, probe, hooks, provider facets
- [x] 4.3 Contracts and frontend codegen; architecture page on agent facets; agents guide
