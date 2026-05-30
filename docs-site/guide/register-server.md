# Register a Server

Once the daemon is running, you can register upstream MCP servers with the `coffer mcp add` command. Registered servers are immediately available to any connected client through the shim.

## Quickstart

Register your first MCP server — using `@modelcontextprotocol/server-filesystem` as the example:

```bash
coffer mcp add filesystem \
  --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"

coffer mcp list                   # → filesystem  | stdio | enabled
coffer mcp tool list filesystem   # → read_file, write_file, list_directory, …
```

- `coffer mcp add` registers the server and stores its transport configuration. The `--stdio` flag tells Coffer to launch the server as a subprocess using the given command.
- `coffer mcp list` shows all registered servers and their current status.
- `coffer mcp tool list <name>` queries the live server and lists the tools it exposes.

The server name (`filesystem` in this example) becomes the namespace prefix that clients use to call its tools — for example, `filesystem__read_file`.

[Connect a client →](/guide/connect-client)
