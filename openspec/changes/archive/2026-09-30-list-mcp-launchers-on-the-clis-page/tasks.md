## 1. Backend

- [x] 1.1 List enabled stdio MCP servers' launchers as required commands (`launcher_cli`, `McpLaunchersPort`, `McpStdioLaunchers`)
- [x] 1.2 Serve `needed_by_servers` on `/api/v1/clis` and in `coffer cli list|show`; drop the login line from `coffer cli show`
- [x] 1.3 Name the MCP servers in the hand-off prompt; no `cli_*` attention item for a command only servers need
- [x] 1.4 Word the missing-launcher attention reason "isn't found on this machine"

## 2. Web

- [x] 2.1 Needed by lists the MCP servers (linked, with "starts with <launcher>") beside the skills; kind badges when both
- [x] 2.2 Header, list row and banner count and name the servers; the banner is a plain sentence
- [x] 2.3 Remove the login command row and every "run it in a terminal" line
- [x] 2.4 MCP servers list row: "<runner> isn't found on this machine" (en/zh)

## 3. Docs and contract

- [x] 3.1 `make contracts`, `make docs-reference`
- [x] 3.2 guides/clis, guides/mcp-servers, coffer-guide skill
