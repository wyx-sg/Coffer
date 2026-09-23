# Connect a Client

Use `coffer-mcp-shim` as the stdio MCP server command in your AI client. The shim auto-discovers (and if needed, auto-spawns) the daemon — no port or token config required.

## Recommended: install it from Coffer

For a registered [agent](/guide/agents), let Coffer write the entry:

```bash
coffer agent mcp install claude-code
```

This writes a `coffer` entry that runs the shim by its absolute path with `--agent-uid <uid>`, so the daemon knows which agent the session belongs to and serves it every server whose reach includes that agent.

## Manual entry

A hand-written entry carries no agent identity. That session sees only the servers whose reach is every agent; a server limited to selected agents stays hidden from it.

### Claude Code

```bash
claude mcp add coffer coffer-mcp-shim
```

### Codex

`~/.codex/config.toml`:

```toml
[mcp_servers.coffer]
command = "coffer-mcp-shim"
```

Restart the client after editing its config. Tools appear namespaced as `<server-name>__<tool-name>` (e.g. `filesystem__read_file`).

Replace `coffer-mcp-shim` with the binary's absolute path if it is not on the client's `PATH`. Several clients can connect at once; each session gets its own set of upstream server processes, so one client never disturbs another.

## Verify it works

1. List the client's tools. Enabled upstream tools appear with their server prefix — `filesystem__read_file`, `filesystem__write_file`, and so on. When the catalogue is larger than the listing budget, the rest stay callable but unlisted; `coffer__search_tools` finds them by description.
2. Ask the agent to read a file. It calls `filesystem__read_file`, and Coffer routes the call to the upstream under its original name.
3. Run `coffer mcp invocations filesystem` — the call is there with its time, duration and outcome.

## Over HTTP

A client that speaks HTTP MCP can skip the shim and connect to `http://127.0.0.1:8000/mcp` (or whichever port `~/.coffer/daemon.json` names). The endpoint requires an `X-Coffer-Token` header carrying the `token` from that same file, and the token changes every time the daemon starts — which is why the shim, which reads it for you, is the recommended path.

## How the shim works

When an MCP client starts a session, it launches `coffer-mcp-shim` as a subprocess. The shim checks `~/.coffer/daemon.json` to find the running daemon. If the daemon is not running, the shim spawns it automatically. Once connected, the shim forwards `stdin/stdout` to the daemon's HTTP/SSE endpoint, bridging the client's stdio MCP protocol to the daemon.

This means you never have to configure a port or token in your client — the shim handles discovery transparently.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `command not found: coffer-mcp-shim` | The shim is not on the client's `PATH` | Use its absolute path in the client config. |
| A disabled tool still appears | The client cached its tool list | Restart the client, or use its "reload MCP servers" option. |

[Agents →](/guide/agents)
