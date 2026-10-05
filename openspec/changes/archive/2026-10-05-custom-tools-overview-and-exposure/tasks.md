## 1. Backend

- [x] 1.1 `current_tools` reads a custom-tool group's tools from its config
- [x] 1.2 The exposure route checks a group's tool names against its config (`set_exposure(..., known=)`)
- [x] 1.3 Tests: the route on a group nobody has listed; the gateway honouring a group tool's exposure end to end

## 2. Frontend

- [x] 2.1 Restore the group page's tabs (Overview, Tools) with the tab in the path (`custom-tools/:group/:tab`)
- [x] 2.2 Extract the MCP Overview's Last 24 hours block into a shared component
- [x] 2.3 Group Overview: definition, Last 24 hours, Requires, Most-called tools
- [x] 2.4 Tools tab: the exposure control on each tool
- [x] 2.5 Tests for the two tabs, the Overview blocks and the exposure control

## 3. Specs and docs

- [x] 3.1 web-ui and mcp-gateway deltas; rename "Manage custom tool groups on one page" back and update its citations
- [x] 3.2 docs-site guides (en + zh)
