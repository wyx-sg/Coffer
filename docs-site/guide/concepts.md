# Concepts

Four core concepts underpin how Coffer works. Understanding them helps you reason about what happens when you register a server, connect a client, or inspect the daemon's state.

## Resource kind

Every user-managed entity in Coffer is a **Resource** identified by `<kind>:<name>`. The resource framework unifies identity, lifecycle (register / update / enable / disable / delete), audit, and schema validation across all kinds.

The only kind shipping today is `mcp_server` — a registered upstream MCP server that carries its transport configuration, credential references, and per-server policies. The framework is kind-agnostic: adding a new kind in the future requires no changes to the core resource machinery.

## Gateway (daemon)

The **gateway** is the long-lived FastAPI daemon that runs on `127.0.0.1:<auto-port>`. It owns all state (stored in SQLite at `~/.coffer/coffer.db`), aggregates upstream MCP servers, and re-exposes their tools through a unified `/mcp` HTTP/SSE endpoint.

Because the daemon is the single writer, all registered clients see a consistent, up-to-date view of your servers. The daemon is started with `coffer daemon start` and discovered by other processes through `~/.coffer/daemon.json` (PID + port + token, mode `0600`).

## Shim

`coffer-mcp-shim` is the short-lived stdio forwarder that bridges an MCP client session to the daemon. Each MCP client process gets its own shim instance, whose lifetime is bound to that client session.

When the shim starts, it checks `~/.coffer/daemon.json`. If the daemon is not running, the shim spawns it. The shim then forwards the client's `stdin/stdout` to the daemon's HTTP/SSE endpoint, translating between the stdio MCP protocol and HTTP transparently. This is why clients need only a single line of configuration — the shim handles discovery and connection automatically.

## Local-first

All user state lives on the user's machine. Cloud services — LLMs, tool APIs — are providers only; they never become the system of record for any vault state. The HTTP API binds exclusively to `127.0.0.1`.

This means your list of registered servers, your credentials, and your audit history are never sent to a vendor's cloud. Replicating user state to a vendor-controlled cloud is a constitutional amendment — not a configuration option.
