## 1. Backend

- [x] 1.1 Parsed MCP entries keep `cwd` and every other key (`extra`, plain values, out of `repr`); `masked_extra` withholds secret-looking values
- [x] 1.2 `AgentMcpEntryService.get_entry` locates one entry (source-disambiguated, `coffer` protected) and annotates `matches_resource`
- [x] 1.3 `GET /agents/{uid}/mcp-entries/{entry}` returning `McpEntryDetail`; contract YAML + codegen
- [x] 1.4 `coffer agent mcp show-entry`

## 2. Frontend

- [x] 2.1 `agentsApi.mcpEntry`, `agentMcpEntryKey`, `useAgentMcpEntry`
- [x] 2.2 `AgentMcpEntryPage` at `/agents/:uid/mcp-servers/:entry` with `AgentMcpEntryOverview`; adopt navigates to the new server, delete back to the tab
- [x] 2.3 Direct servers table: the name links to the page with the way back in router state
- [x] 2.4 en/zh strings

## 3. Tests and docs

- [x] 3.1 Domain unit tests, route and CLI integration tests, page tests, with acceptance markers
- [x] 3.2 Agents guide and CLI reference
