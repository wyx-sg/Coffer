# Surfaces

::: tip Mental model
Every surface in Coffer is an entry point into the same underlying daemon. The daemon owns all state; surfaces are read-only or read-write windows into that state. Add an MCP server via the CLI, and the Web UI shows it immediately — because both are calling the same daemon. Close the browser tab, and the daemon keeps running, so your MCP clients keep working.
:::

## What surfaces share

All surfaces sit on top of the same `coffer-daemon` process. The daemon is a FastAPI application bound to `127.0.0.1:<auto-port>` and exposing two top-level endpoint groups:

- `/api/v1/*` — the management plane (REST, JSON), authenticated with `X-Coffer-Token`.
- `/mcp` — the MCP protocol endpoint (HTTP/SSE), also authenticated with `X-Coffer-Token`.

Every surface communicates with the daemon over loopback HTTP, reading the port and token from `~/.coffer/daemon.json` (mode `0600`, owner-readable only). No surface has its own persistent state — they are stateless entry points into the daemon's stateful core.

The surfaces are described below using a consistent template: **What it is · Which process · Transport · Lifecycle · Security boundary**.

---

## REST API

**What it is.** The management plane. This is the HTTP JSON API through which every resource-kind and cross-cutting operation is performed. It is organized into route groups under `/api/v1/`, one family per kind plus the shared concerns:

| Route group                       | Covers                                                              |
| --------------------------------- | ------------------------------------------------------------------ |
| `/resources`                      | Kind-agnostic resource CRUD, enable/disable, lifecycle.            |
| `/resources/mcp_server`           | MCP capability preferences and invocation logs.                   |
| `/agents`                         | Agent registry, config files, workspace facets.                    |
| `/skills`                         | Skill master store and per-agent bindings.                        |
| `/knowledge/{scope}`              | One knowledge scope: `entries`, `documents`, retrieval, organize, reindex. |
| `/channels`                       | Channel bindings (Telegram, SeaTalk), pairing.                    |
| `/agent-providers`, `/models`     | The registered agent providers with their model catalogues; connection introspection. |
| `/credentials`, `/settings`       | Encrypted credential store; settings incl. `/settings/credentials` (master-key storage) and `/embedding` config. |
| `/sync`                           | Vault export / import runs and the master-key transfer.           |
| `/fs`                             | Filesystem browse helper for config pickers.                      |
| `/audit`, `/retention`, `/daemon` | Audit log, retention policies, daemon token operations.           |

The REST API is the canonical interface — the CLI and the Web UI both call it.

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

**What it is.** The command-line management interface. Every management operation available through the REST API is also available as a `coffer` subcommand, grouped to mirror the kinds and cross-cutting concerns:

- **Per-kind groups:** `coffer mcp`, `coffer agent`, `coffer skill`, `coffer knowledge`, `coffer channel`.
- **Cross-cutting groups:** `coffer credentials`, `coffer sync`, `coffer provider`, `coffer scope`.
- **Kind-agnostic / operational groups:** `coffer resource`, `coffer audit`, `coffer retention`, `coffer daemon`, `coffer open`. Reindexing a single knowledge scope is `coffer knowledge reindex`.

Typical commands read as `coffer mcp add`, `coffer mcp tool enable/disable`, `coffer audit`, `coffer daemon start/stop/status`. The CLI is Coffer's primary interface for scripted workflows, dotfile-based setup, and remote (headless) machines where a browser is not available. Every subcommand supports `--json` output for machine-readable integration.

**Which process.** A short-lived child process. The CLI is an independent Python process, installed on `PATH` as a console script entry point (`coffer`). It exits after executing one command. It does not stay running between invocations.

**Transport.** Loopback HTTP to `127.0.0.1:<port>/api/v1/`, using the token from `~/.coffer/daemon.json`. The CLI uses the detect-or-spawn pattern: if the daemon is not running when a CLI command is issued, the CLI spawns the daemon as a detached background process, waits for `daemon.json` to appear, and then connects. The user never sees "daemon not running" as an error; they may see a brief startup delay on first invocation.

**Lifecycle.** Spawned on demand; exits after each command completes (or after printing an error). The CLI's exit does not stop the daemon.

**Security boundary.** Token from `~/.coffer/daemon.json` (mode `0600`). The same file-permission boundary as every other surface: only the owner of the user account can read the token and therefore issue authenticated requests.

---

## Stdio Shim (`coffer-mcp-shim`)

**What it is.** The bridge between MCP clients (Claude Code, Codex, and any other tool that supports stdio MCP servers) and the daemon's MCP endpoint. MCP clients are configured with `"command": "coffer-mcp-shim"` instead of a specific upstream server. The shim translates between the client's stdin/stdout interface and the daemon's HTTP/SSE MCP endpoint, making the daemon look like a regular stdio MCP server from the client's perspective.

**Which process.** One shim process per connected MCP client session. A new shim process is spawned by each MCP client on client startup. Three MCP clients running simultaneously means three shim processes, each maintaining its own HTTP/SSE connection to the daemon, each resulting in its own independent `MCPGatewaySession` with its own upstream subprocess set.

**Transport.** The shim reads from stdin and writes to stdout (as far as the MCP client is concerned). Internally, it connects to `127.0.0.1:<port>/mcp` over HTTP/SSE, carrying the `X-Coffer-Token`. JSON-RPC messages arriving on stdin are forwarded as HTTP POST requests to the daemon; notifications from the daemon's SSE stream are written back to stdout.

**Lifecycle.** The shim is spawned by the MCP client using whatever subprocess mechanism that client supports (e.g., `claude mcp add coffer coffer-mcp-shim` for Claude Code). It exits when the MCP client process exits. Its exit does not stop the daemon — other shims and other clients continue unaffected. On startup, the shim applies detect-or-spawn: if no running daemon is found in `daemon.json`, it spawns one, then connects.

**Security boundary.** Same as the CLI: token from `~/.coffer/daemon.json`, file-permission boundary. Because the shim is spawned by the MCP client (which runs as the same local user), the trust boundary is implicit in the process ownership chain. The shim carries the token on every request to the daemon; the daemon validates it.

---

## Callback Listener

**What it is.** The only public-reachable surface. It is a separate signed-callback process that receives inbound webhooks from chat platforms — concretely `POST /seatalk/{channel}` — verifies each request's SeaTalk signature against the channel's signing secret, answers the `event_verification` challenge, and forwards genuine events to the daemon for the channel runtime to handle. It exists because SeaTalk pushes events to a URL rather than letting Coffer long-poll (the model Telegram uses), so a reachable HTTP endpoint is required (spec channels, [Channel Adapter Framework](/reference/adr/channel-adapter-framework)).

**Which process.** A daemon-spawned child process, deliberately separate from the daemon. It runs only while at least one SeaTalk channel is enabled. Keeping it out of the main daemon means the public-reachable code path is a small, isolated surface that handles signature verification before anything reaches the stateful core.

**Transport.** HTTP on `127.0.0.1:<callback-port>`, serving only the signed callback paths. The listener itself binds to loopback; reachability from SeaTalk's servers is provided by a **user-run tunnel** the owner stands up out-of-band — Coffer never opens a public port itself.

**Lifecycle.** Spawned by the daemon when a SeaTalk channel is enabled; torn down when the last SeaTalk channel is disabled. Its lifetime is bound to channel state, not to any client session.

**Security boundary.** Unlike the loopback surfaces, this one accepts traffic that originates off-machine, so its trust boundary is the **per-channel SeaTalk signature**: every request body is verified with `verify_seatalk_signature` against the channel's secret before it is forwarded, and unsigned or mis-signed requests are rejected. The `X-Coffer-Token` is not the gate here — the signature is.

---

## Web UI

**What it is.** The browser-based management interface, specified in [spec ui-shell](/reference/specs/ui-shell/spec). The Web UI provides a visual equivalent of every CLI management operation: registering MCP servers via JSON import, browsing server health and capability lists, toggling tools/resources/prompts on/off, viewing the audit log and invocation history, and configuring retention policies. The information architecture reflects the resource-kind model: the sidebar shows `Agents` (agents and the Channels they are reached over), `Resources` (the shipped kinds — MCP servers, Skills, Knowledge), and `System` (Audit log and Settings). No "coming soon" placeholders appear — a kind only appears once it works, and none outlives its feature.

**Which process.** A browser process, served by the daemon. In production the daemon serves the built frontend itself, as static files at its own loopback origin (**FR-024**) — so the page and the API are same-origin. In development, a Vite dev server runs at `http://localhost:5173` and reaches the daemon across origins behind the `COFFER_DEV_CORS` opt-in. All data is fetched from the daemon's REST API.

**Transport.** Browser HTTP/REST to `http://127.0.0.1:<port>/api/v1/`, from a page loaded at `http://127.0.0.1:<port>/`.

**How the token reaches the page.** The daemon injects its live API token into the `index.html` it serves, as a `window.__COFFER_TOKEN__` global in the document head (**FR-025**) — on the bare `/` and on every client-side route served through the SPA fallback alike, `no-store` and without validators so a cached copy can never carry a restarted daemon's dead token. Any page the daemon serves is therefore authenticated by the act of being served; the token appears in no URL and in no browser storage. `coffer open` (**FR-025**) carries no credential — it reads the daemon's real port from `~/.coffer/daemon.json`, which moves between restarts, and opens the browser there.

**Lifecycle.** The Web UI session is the lifetime of the browser tab. Closing the tab does not affect the daemon. The UI includes a daemon-offline banner that detects when the daemon is unreachable and displays the `coffer daemon start` command as a copyable affordance; the banner disappears automatically when the daemon comes back online.

**Security boundary.** `X-Coffer-Token` on every REST API call. CORS is same-origin by default; the Vite dev origins are added only under `COFFER_DEV_CORS`. Because the served page now carries the token, the daemon also refuses any request whose `Host` header is not a loopback authority (**FR-027**), which is what closes DNS rebinding — a browser treats a rebound `evil.com` as same-origin, but still sends `Host: evil.com`. Because the daemon binds to loopback and the token is never transmitted to a remote origin, the trust model is equivalent to the CLI: local user account only.

---

## Surface comparison

| Surface        | Process type      | Transport to daemon        | Spawned by          | Lifecycle           |
| -------------- | ----------------- | -------------------------- | ------------------- | ------------------- |
| REST API       | Daemon            | — (is the daemon)          | System / manual     | Daemon lifetime     |
| MCP endpoint   | Daemon            | — (is the daemon)          | System / manual     | Daemon lifetime     |
| CLI (`coffer`) | Short-lived child | Loopback HTTP              | User / shell        | Per-command         |
| Stdio shim     | Per-session       | HTTP/SSE                   | MCP client          | MCP client session  |
| Callback listener | Daemon-spawned child | Loopback HTTP (forwards to daemon) | Daemon (on SeaTalk enable) | While a SeaTalk channel is enabled |
| Web UI         | Browser tab       | Loopback HTTP (REST)       | `coffer open` / browser | Browser tab session |

---

**See also:** [Architecture reference](/reference/project/architecture), [UI Shell spec](/reference/specs/ui-shell/spec), [Distribution](/architecture/distribution)
