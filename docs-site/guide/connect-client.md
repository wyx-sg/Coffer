# Connect a Client

Use `coffer-mcp-shim` as the stdio MCP server command in your AI client. The shim auto-discovers (and if needed, auto-spawns) the daemon — no port or token config required.

## Claude Code

```bash
claude mcp add coffer coffer-mcp-shim
```

## Codex

`~/.codex/config.toml`:

```toml
[mcp_servers.coffer]
command = "coffer-mcp-shim"
```

Restart the client after editing its config. Tools appear namespaced as `<server-name>__<tool-name>` (e.g. `filesystem__read_file`).

## How the shim works

When an MCP client starts a session, it launches `coffer-mcp-shim` as a subprocess. The shim checks `~/.coffer/daemon.json` to find the running daemon. If the daemon is not running, the shim spawns it automatically. Once connected, the shim forwards `stdin/stdout` to the daemon's HTTP/SSE endpoint, bridging the client's stdio MCP protocol to the daemon.

This means you never have to configure a port or token in your client — the shim handles discovery transparently.
