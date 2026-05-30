# Surfaces

::: tip Mental model
Every surface in Coffer is an entry point into the same underlying daemon. The daemon owns all state; surfaces are read-only or read-write windows into that state. Add an MCP server via the CLI, and the Web UI shows it immediately — because both are calling the same daemon. Disconnect from the desktop app, and the daemon keeps running, so your MCP clients keep working.
:::

## What surfaces share

All surfaces sit on top of the same `coffer-daemon` process. The daemon is a FastAPI application bound to `127.0.0.1:<auto-port>` and exposing two top-level endpoint groups:

- `/api/v1/*` — the management plane (REST, JSON), authenticated with `X-Coffer-Token`.
- `/mcp` — the MCP protocol endpoint (HTTP/SSE), also authenticated with `X-Coffer-Token`.

Every surface communicates with the daemon over loopback HTTP, reading the port and token from `~/.coffer/daemon.json` (mode `0600`, owner-readable only). No surface has its own persistent state — they are stateless entry points into the daemon's stateful core.

The six surfaces are described below using a consistent template: **What it is · Which process · Transport · Lifecycle · Security boundary**.

---

## REST API

**What it is.** The management plane. This is the HTTP JSON API through which all resource management operations are performed: registering, listing, updating, enabling, disabling, and deleting MCP servers; reading and modifying capability preferences; viewing audit and invocation logs; managing retention policies; rotating the daemon auth token; and initiating database backups. The REST API is the canonical interface — the CLI, Web UI, and Desktop all call it.

**Which process.** The daemon (`coffer-daemon`). The REST API is embedded in the FastAPI application and is inseparable from the daemon process.

**Transport.** HTTP/1.1 on `127.0.0.1:<auto-port>`. All endpoints are under `/api/v1/`. JSON request and response bodies. No WebSocket; no SSE on the management plane.

**Lifecycle.** The REST API is available from the moment the daemon reaches "ready" state. It shuts down when the daemon shuts down.

**Security boundary.** Every request must carry a valid `X-Coffer-Token` header. The token is generated at daemon startup, stored in `~/.coffer/daemon.json`, and never transmitted outside the machine. CORS is configured to allow requests from the local Web UI origin only. Because the daemon binds exclusively to `127.0.0.1`, the network itself is a first-line defense: no request from another machine on the network can reach the API.

---

## MCP Protocol Endpoint

**What it is.** The aggregated MCP surface. This is the endpoint that MCP clients ultimately talk to. It accepts JSON-RPC 2.0 messages over HTTP/SSE and speaks the full MCP protocol: `initialize` handshake, `tools/list`, `tools/call`, `resources/list`, `resources/read`, `prompts/list`, `prompts/get`, and `notifications/*`. The daemon aggregates tools, resources, and prompts from all registered upstream MCP servers, namespacing each with `<server-name>__<capability-name>`, and presents them as if they came from a single MCP server.

**Which process.** The daemon. The MCP endpoint is part of the same FastAPI application as the REST API, served on the same port.

**Transport.** HTTP/SSE on `127.0.0.1:<auto-port>/mcp`. MCP uses HTTP POST for JSON-RPC requests and Server-Sent Events for streaming notifications back to the client (such as `tools/list_changed`). The stdio shim bridges its stdin/stdout to this HTTP/SSE endpoint.

**Lifecycle.** A new `MCPGatewaySession` is created when a client connects (via the `/mcp` endpoint or through the shim). The session is disposed when the client disconnects. Upstream subprocesses owned by the session are reaped on disposal. The MCP endpoint itself lives as long as the daemon.

**Security boundary.** The `X-Coffer-Token` is required on the initial connection. Because connections arrive through the stdio shim (which reads the token from `daemon.json`) or directly from a local process, the effective trust boundary is the local user account. Each session is isolated: one client's upstream subprocesses and capability caches are invisible to another client's session.

---

## CLI (`coffer …`)

**What it is.** The command-line management interface. Every management operation available through the REST API is also available as a `coffer` subcommand: `coffer mcp add`, `coffer mcp list`, `coffer mcp tool list`, `coffer mcp tool enable/disable`, `coffer audit`, `coffer retention`, `coffer daemon start/stop/status`. The CLI is Coffer's primary interface for scripted workflows, dotfile-based setup, and remote (headless) machines where a browser is not available. Every subcommand supports `--json` output for machine-readable integration.

**Which process.** A short-lived child process. The CLI is an independent Python process, installed on `PATH` as a console script entry point (`coffer`). It exits after executing one command. It does not stay running between invocations.

**Transport.** Loopback HTTP to `127.0.0.1:<port>/api/v1/`, using the token from `~/.coffer/daemon.json`. The CLI uses the detect-or-spawn pattern: if the daemon is not running when a CLI command is issued, the CLI spawns the daemon as a detached background process, waits for `daemon.json` to appear, and then connects. The user never sees "daemon not running" as an error; they may see a brief startup delay on first invocation.

**Lifecycle.** Spawned on demand; exits after each command completes (or after printing an error). The CLI's exit does not stop the daemon.

**Security boundary.** Token from `~/.coffer/daemon.json` (mode `0600`). The same file-permission boundary as every other surface: only the owner of the user account can read the token and therefore issue authenticated requests.

---

## Stdio Shim (`coffer-mcp-shim`)

**What it is.** The bridge between MCP clients (Claude Code, Codex, Cursor, and any other tool that supports stdio MCP servers) and the daemon's MCP endpoint. MCP clients are configured with `"command": "coffer-mcp-shim"` instead of a specific upstream server. The shim translates between the client's stdin/stdout interface and the daemon's HTTP/SSE MCP endpoint, making the daemon look like a regular stdio MCP server from the client's perspective.

**Which process.** One shim process per connected MCP client session. A new shim process is spawned by each MCP client on client startup. Three MCP clients running simultaneously means three shim processes, each maintaining its own HTTP/SSE connection to the daemon, each resulting in its own independent `MCPGatewaySession` with its own upstream subprocess set.

**Transport.** The shim reads from stdin and writes to stdout (as far as the MCP client is concerned). Internally, it connects to `127.0.0.1:<port>/mcp` over HTTP/SSE, carrying the `X-Coffer-Token`. JSON-RPC messages arriving on stdin are forwarded as HTTP POST requests to the daemon; notifications from the daemon's SSE stream are written back to stdout.

**Lifecycle.** The shim is spawned by the MCP client using whatever subprocess mechanism that client supports (e.g., `claude mcp add coffer coffer-mcp-shim` for Claude Code). It exits when the MCP client process exits. Its exit does not stop the daemon — other shims and other clients continue unaffected. On startup, the shim applies detect-or-spawn: if no running daemon is found in `daemon.json`, it spawns one, then connects.

**Security boundary.** Same as the CLI: token from `~/.coffer/daemon.json`, file-permission boundary. Because the shim is spawned by the MCP client (which runs as the same local user), the trust boundary is implicit in the process ownership chain. The shim carries the token on every request to the daemon; the daemon validates it.

---

## Web UI

**What it is.** The browser-based management interface, specified in [spec 002](/reference/specs/002-ui-shell/spec). The Web UI provides a visual equivalent of every CLI management operation: registering MCP servers via JSON import, browsing server health and capability lists, toggling tools/resources/prompts on/off, viewing the audit log and invocation history, and configuring retention policies. The information architecture reflects the resource-kind model: the sidebar shows `Resources` (MCP servers, and future kinds as they ship) and `System` (Observability, Settings). No "coming soon" placeholders appear.

**Which process.** A browser process. In production, the built frontend is embedded by the Tauri desktop shell (`frontendDist` in `tauri.conf.json`); the browser process is logically separate from the daemon. In development, a Vite dev server runs at `http://localhost:5173`. All data is fetched from the daemon's REST API.

**Transport.** Browser HTTP/REST to `http://127.0.0.1:<port>/api/v1/`. The bearer token is provided to the browser context at startup (read from `~/.coffer/daemon.json` by the desktop shell or a local helper).

**Lifecycle.** The Web UI session is the lifetime of the browser tab. Closing the tab does not affect the daemon. The UI includes a daemon-offline banner that detects when the daemon is unreachable and displays the `coffer daemon start` command as a copyable affordance; the banner disappears automatically when the daemon comes back online.

**Security boundary.** `X-Coffer-Token` on every REST API call. CORS is configured to allow requests from the local Web UI origin only. Because the daemon binds to loopback and the token is never transmitted to a remote origin, the trust model is equivalent to the CLI: local user account only.

---

## Desktop App

**What it is.** The Tauri 2 desktop application, specified in [spec 003](/reference/specs/003-mcp-gateway-desktop/spec). The desktop app wraps the same Web UI from spec 002 inside a native application window, adds daemon supervision, a system tray icon, and optional launch-at-login. It is the zero-friction entry point for daily-driver desktop use: install it, and Coffer is always running in the background without any manual `coffer daemon start` step.

**Which process.** A native desktop process (Tauri 2, Rust + WebView). It embeds the Web UI as a WebView; desktop-specific affordances (tray menu items, autostart settings) activate behind an `isTauri()` guard in the frontend code.

**Transport.** Internally: the WebView talks to `127.0.0.1:<port>/api/v1/` for REST and `/mcp` for MCP (same as the browser-based Web UI). The Rust shell also communicates with the daemon's REST API for supervision tasks (health checks, restart).

**Lifecycle.** The desktop app applies the detect-or-spawn pattern: on launch, it reads `daemon.json`; if the daemon is already running, it connects; if not, it spawns `coffer-daemon` as a detached process (`setsid` on POSIX, `DETACHED_PROCESS` on Windows) and waits for `daemon.json` to appear. Closing the main window hides it to the system tray — the daemon keeps running. Selecting "Quit" from the tray exits the desktop process. The daemon's fate on desktop-app quit depends on whether any other entry points (shim, CLI) are still using it; a detached daemon survives the desktop app.

The desktop app also idempotently deploys the bundled `coffer-mcp-shim` binary to a stable user-writable PATH directory (`~/.coffer/bin/` on macOS/Linux; `%LOCALAPPDATA%\Coffer\bin\` on Windows) on every launch, using a size-mismatch heuristic to detect upgrades. This ensures that `coffer-mcp-shim` is always on PATH after the first desktop launch, without requiring the user to manually edit their shell profile.

**Security boundary.** Same as the Web UI: `X-Coffer-Token` on every API call, loopback-only daemon, local user account trust boundary. The desktop app bundles `coffer-daemon` and `coffer-mcp-shim` as PyInstaller sidecars — no system Python dependency at runtime.

**Distribution tiers.** The desktop app is the CLI+desktop tier of the release. A separate CLI-only tier (`coffer-cli-<triple>.tar.gz` / `.zip`) packages just the two binaries without the Tauri wrapper, for headless or server installs.

---

## Surface comparison

| Surface        | Process type      | Transport to daemon        | Spawned by          | Lifecycle           |
| -------------- | ----------------- | -------------------------- | ------------------- | ------------------- |
| REST API       | Daemon            | — (is the daemon)          | System / manual     | Daemon lifetime     |
| MCP endpoint   | Daemon            | — (is the daemon)          | System / manual     | Daemon lifetime     |
| CLI (`coffer`) | Short-lived child | Loopback HTTP              | User / shell        | Per-command         |
| Stdio shim     | Per-session       | HTTP/SSE                   | MCP client          | MCP client session  |
| Web UI         | Browser tab       | Loopback HTTP (REST)       | User / browser      | Browser tab session |
| Desktop app    | Native process    | Loopback HTTP (REST + MCP) | User / OS autostart | Until tray quit     |

---

**See also:** [Architecture reference](/reference/project/architecture), [Spec 002: UI Shell](/reference/specs/002-ui-shell/spec), [Spec 003: Desktop](/reference/specs/003-mcp-gateway-desktop/spec)
