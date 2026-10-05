## Context

Tool exposure (mcp-gateway "Choose how each tool is exposed") is a per-(server, tool) override kept in the server's `mcp-preferences` vault document (`tool_exposure`), keyed by the server's uid. The gateway turns it into namespaced overrides (`exposure_overrides`) over every server visible to the session, and both `tools/list` tiering and `coffer__search_tools` read them. A custom tool group is an `mcp_server` resource with the `http_api` transport, so its tools already appear in the gateway as `<group>__<tool>` and pass through the same tiering.

## Decisions

### Reuse the server's exposure, keyed by the group's uid

No new key, store, route or audit event. The group's uid is its server uid; the existing routes `PATCH /api/v1/resources/mcp_server/{uid}/tools/{tool}/exposure` (and the batch form) and `GET .../tiering` address the group as they address any server, the setting lands in the group's `mcp-preferences` document, and each change is audited as `tool_exposure_changed`. The gateway needed no change: `_servers_and_hidden` already builds overrides over every visible server, groups included.

### A group's tools come from its config, not from discovery

Two reads asked discovery's saved tool list for "the tools this server offers": the route's unknown-tool check (`set_exposure`) and the tiering read's catalogue (`current_tools`). Discovery only saves a list once an agent has listed the server, so a group nobody had listed yet refused every exposure with 404 and reported no tools. A group's tools are its own config, served in-process from it, so both reads now take them from there: `current_tools` returns the config's tools with their switch for an `http_api` server, and the exposure route passes the config's tool names to `set_exposure(..., known=...)`. Every other server keeps the discovery-saved list.

### The page reads what the MCP server page reads

The group's Overview and Tools tab use the MCP server page's reads by the group's uid — `invocations/summary` for Last 24 hours, `tiering` for each tool's listed / behind-search state and exposure — so no route is added. Requires is built from the group's own read (each secret header's state, already computed for the banners) rather than the MCP status read, because a group has no launcher and its secret states are already on the group.

## Risks

- An exposure set on a tool that is later deleted or renamed stays in the document until the tool's name is reused, as for a tool an MCP server stops offering; it never affects another tool.
