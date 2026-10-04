## 1. Backend

- [x] 1.1 Remove the tool reach repository, its port, route, schemas and view fields
- [x] 1.2 Gate a custom tool on its switch only; re-import keeps switch and changes-data flag
- [x] 1.3 Regenerate the mcp-gateway contract and the frontend types; update data models
- [x] 1.4 Tests: drop override tests, cover "every tool that is on follows its group's reach"

## 2. Frontend

- [x] 2.1 Drop the tools table's reach column, ToolReachCell, useToolReach and the inherited reach control
- [x] 2.2 `?agent=` filter and pill on the Custom tools list
- [x] 2.3 Multi-select and the selection bar (Reach, Delete, clear) on the group list
- [x] 2.4 Custom-tool From Coffer row on the agent MCP servers tab; MCP row excludes groups
- [x] 2.5 Tools table search and Add request above the table
- [x] 2.6 i18n en + zh and tests for the new scenarios

## 3. Docs and design

- [x] 3.1 docs-site guides (custom tools, web UI, agents) and architecture, en + zh; `.agents/frontend.md`, `docs-site/contributing/frontend.md`
- [x] 3.2 Capabilities canvas (custom tools list, group page) and Agents canvas (MCP servers tab)
- [x] 3.3 `make verify`, archive the change
