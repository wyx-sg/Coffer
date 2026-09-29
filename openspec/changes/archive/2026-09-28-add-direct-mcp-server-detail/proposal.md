## Why

The agent's MCP servers tab lists the servers configured directly in the agent's own config files as one line each — a name, a transport chip and a truncated command. Everything else the file says about a server (its full arguments, working directory, environment and header names, other keys, and which file it lives in) could only be found by opening the file by hand. A direct server needs a detail page of its own, like a managed one has.

## What Changes

- `GET /agents/{uid}/mcp-entries/{entry}?source=` reads one direct MCP entry in full: every listing field plus the config file's absolute `path`, `cwd`, and every other key as `extra`. Env and header values stay names-only; any other secret-looking value is masked by the daemon.
- `coffer agent mcp show-entry <agent> <entry> [--source] [--json]` prints the same, never a secret value.
- A new page, `/agents/{uid}/mcp-servers/{entry}?source=`, opened by clicking a direct server's name: a header with the name, a "direct server of <agent>" badge, the back link to the agent's MCP servers tab, and the adopt / delete actions; a body with the configuration and the config file (open in editor, reveal). Adopting moves on to the new managed server's page; deleting returns to the tab.

## Capabilities

### New Capabilities

### Modified Capabilities
- `agent-registry`: adds "Show one direct MCP entry's full configuration without its secrets"; "Expose every agent operation through REST, CLI and the Agents page" gains the entry view.

## Impact

- Backend: `domain/agent/mcp_entries.py` (entries keep `cwd` and their other keys; masking), `AgentMcpEntryService.get_entry`, the agent workspace route and CLI command.
- Contract: `agent-registry` `api.openapi.yaml` gains the GET operation and the `McpEntryDetail` / `McpEntryField` schemas; frontend codegen.
- Frontend: `AgentMcpEntryPage`, `AgentMcpEntryOverview`, the Direct servers table's name link, the adopt dialog's `onAdopted`, en/zh strings.
- Docs: the Agents guide and the CLI reference.
