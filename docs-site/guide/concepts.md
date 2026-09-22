# Concepts

Four core concepts underpin how Coffer works. Understanding them helps you reason about what happens when you register a server, connect a client, or inspect the daemon's state.

## Resource kind

Every user-managed entity in Coffer is a **Resource** identified by an immutable `uid` — an opaque value minted once and never reused, the same on every machine your vault syncs with. Its **name** is a label you can change at any time — `coffer resource rename <kind> <name> <new-name>`, for any kind — and renaming keeps the resource's identity, so its reach, its credentials, its bindings and its history all follow it. The resource framework unifies identity, lifecycle (register / update / enable / disable / delete), audit, and schema validation across all kinds.

Seven kinds ship today:

- `mcp_server` — a registered upstream MCP server that carries its transport configuration, credential references, and per-server policies.
- `agent` — a registered local AI coding agent (`claude_code` or `codex`) whose curated config files Coffer can view and edit, and into which Coffer can install its own MCP server.
- `skill` — an AgentSkills folder Coffer manages from a single master copy and can deliver to an agent's config directory. Per-agent enable/disable bindings are managed from the agent's detail page.
- `knowledge` — a collection of what your agents know: the files they write and the documents you ingest, as Markdown on disk under `~/.coffer/knowledge/<collection>/`. The files are the only copy — there is no index over them, and search is a literal pass across the files themselves.
- `memory` — one partition of the facts Coffer aggregated out of your agents' *own* native memory, as files under `~/.coffer/memory/`. Derived, never written back into the agent.
- `provider` — a vendor endpoint Coffer holds a key for: `{protocol, base_url, credential_ref}`. One may be marked Coffer's internal default, which is the connection its own unattended passes run on.
- `channel` — a Telegram or SeaTalk binding that lets you reach your agents from a messaging app.

The framework is kind-agnostic: adding a new kind in the future requires no changes to the core resource machinery.

## Gateway (daemon)

The **gateway** is the long-lived FastAPI daemon that runs on `127.0.0.1:8000`. It owns all control-plane state (stored in SQLite at `~/.coffer/coffer.db`), aggregates upstream MCP servers, and re-exposes their tools through a unified `/mcp` HTTP/SSE endpoint.

The port is **fixed**, not scanned: with nothing configured the daemon binds exactly 8000 and refuses to start if it cannot, telling you which process holds the port. That is what makes a bookmark to the web UI keep working — and it is why your UI preferences, which the browser keys by origin, do not silently reset. Pin a different port with `coffer daemon port set <n>`; it is stored in `~/.coffer/daemon-config.json`, the one setting that has to live in a file rather than the database, because the port is chosen before the database is even opened.

Because the daemon is the single writer, all registered clients see a consistent, up-to-date view of your servers. It is discovered by other processes through `~/.coffer/daemon.json` (PID + port + token, mode `0600`).

Any client will start one if none is running — `coffer daemon start`, the desktop app, an agent's MCP shim — but the one worth setting up is `coffer daemon service install`, which makes it a login service so it is already up before the first agent call of the day, and restarts it if it crashes. It stands down again after twelve hours with nothing using it (`coffer daemon idle set <hours>`, or `never`).

## Shim

`coffer-mcp-shim` is the short-lived stdio forwarder that bridges an MCP client session to the daemon. Each MCP client process gets its own shim instance, whose lifetime is bound to that client session.

When the shim starts, it checks `~/.coffer/daemon.json`. If the daemon is not running, the shim spawns it. The shim then forwards the client's `stdin/stdout` to the daemon's HTTP/SSE endpoint, translating between the stdio MCP protocol and HTTP transparently. This is why clients need only a single line of configuration — the shim handles discovery and connection automatically.

## Local-first

All user state lives on the user's machine. Cloud services — LLMs, tool APIs — are providers only; they never become the system of record for any vault state. The HTTP API binds exclusively to `127.0.0.1`.

This means your list of registered servers, your credentials, and your audit history are never sent to a vendor's cloud. Replicating user state to a vendor-controlled cloud is a constitutional amendment — not a configuration option.
