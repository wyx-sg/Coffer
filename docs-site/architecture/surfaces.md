# Surfaces

::: tip Mental model
Every surface in Coffer is an entry point into the same underlying daemon. The daemon owns all state; surfaces are read-only or read-write windows into that state. Add an MCP server via the CLI, and the Web UI shows it immediately — because both are calling the same daemon. Close the browser tab, and the daemon keeps running, so your MCP clients keep working.
:::

## What surfaces share

All surfaces sit on top of the same `coffer-daemon` process. The daemon is a FastAPI application bound to `127.0.0.1:8000` — a **fixed** port it refuses to start without, changeable with `coffer daemon port set` (see [Daemon & processes](/architecture/processes#the-port-is-fixed)) — and exposing two top-level endpoint groups:

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
| `/resources/mcp_server`, `/mcp`   | Per-server capability preferences and invocations; `/mcp/invocations` is the cross-server view. |
| `/agents`                         | Agent registry, config files, workspace facets, plugins, native memory stores, transcripts. |
| `/skills`                         | Skill master store, per-agent bindings, `verify` and `repair`.     |
| `/knowledge`                      | `collections`, `tree`, `file` (read, delete), `material`, `upload`, and `collections/{uid}/curate`. No retrieval route. |
| `/memory`                         | `partitions` and their `notes`, `retired` notes, `files` and `distil`; `sync`, `context`, and per-agent `delivery`. |
| `/channels`                       | Channel bindings (Telegram, SeaTalk), pairing.                    |
| `/chat`                           | Conversations, their messages, and the turn surface the web Chat page drives: fire-and-return `POST .../messages`, SSE `GET .../events`, `PUT .../pending`, `POST .../interrupt`. |
| `/agent-providers`, `/models`     | The registered agent providers with their model catalogues; connection introspection. |
| `/providers`, `/internal-engine-config` | The `provider` kind — vendor endpoints and their keys — and the connection plus model Coffer's own engine runs on. |
| `/credentials`, `/settings`       | Encrypted credential store; settings incl. `/settings/credentials` (master-key storage). |
| `/sync`                           | Converge rounds against the git remote, the remote's configuration, machines, and the master-key transfer. |
| `/upkeep`                         | `runs` — what the unattended passes (curation, distil, aggregate) are doing right now and last did. |
| `/fs`                             | Filesystem browse helper for config pickers.                      |
| `/audit`, `/retention`, `/daemon` | Audit log, retention policies, daemon token operations, daemon logs. |

The REST API is the canonical interface — the CLI and the Web UI both call it.

**Which process.** The daemon (`coffer-daemon`). The REST API is embedded in the FastAPI application and is inseparable from the daemon process.

**Transport.** HTTP/1.1 on `127.0.0.1:8000` (or the port the user pinned). All endpoints are under `/api/v1/`. JSON request and response bodies. No WebSocket; the one SSE stream on the management plane is the Chat page's turn events.

**Lifecycle.** The REST API is available from the moment the daemon reaches "ready" state. It shuts down when the daemon shuts down.

**Security boundary.** Every request must carry a valid `X-Coffer-Token` header. The token is generated at daemon startup, stored in `~/.coffer/daemon.json`, and never transmitted outside the machine. CORS is configured to allow requests from the local Web UI origin only. Because the daemon binds exclusively to `127.0.0.1`, the network itself is a first-line defense: no request from another machine on the network can reach the API.

---

## MCP Protocol Endpoint

**What it is.** The aggregated MCP surface. This is the endpoint that MCP clients ultimately talk to. It accepts JSON-RPC 2.0 messages over HTTP/SSE and speaks the full MCP protocol: `initialize` handshake, `tools/list`, `tools/call`, `resources/list`, `resources/read`, `prompts/list`, `prompts/get`, and `notifications/*`. The daemon aggregates tools, resources, and prompts from all registered upstream MCP servers, namespacing each with `<server-name>__<capability-name>`, and presents them as if they came from a single MCP server.

**Which process.** The daemon. The MCP endpoint is part of the same FastAPI application as the REST API, served on the same port.

**Transport.** HTTP/SSE on `127.0.0.1:8000/mcp` (or the pinned port). MCP uses HTTP POST for JSON-RPC requests and Server-Sent Events for streaming notifications back to the client (such as `tools/list_changed`). The stdio shim bridges its stdin/stdout to this HTTP/SSE endpoint.

**Lifecycle.** A new `MCPGatewaySession` is created when a client connects (via the `/mcp` endpoint or through the shim). The session is disposed when the client disconnects. Upstream subprocesses owned by the session are reaped on disposal. The MCP endpoint itself lives as long as the daemon.

**Security boundary.** The `X-Coffer-Token` is required on the initial connection. Because connections arrive through the stdio shim (which reads the token from `daemon.json`) or directly from a local process, the effective trust boundary is the local user account. Each session is isolated: one client's upstream subprocesses and capability caches are invisible to another client's session.

---

## CLI (`coffer …`)

**What it is.** The command-line management interface. Every management operation available through the REST API is also available as a `coffer` subcommand, grouped to mirror the kinds and cross-cutting concerns:

- **Per-kind groups:** `coffer mcp`, `coffer agent`, `coffer skill`, `coffer knowledge`, `coffer memory`, `coffer provider`, `coffer channel` — one per registered kind.
- **Cross-cutting groups:** `coffer credentials`, `coffer sync`, `coffer scope`, `coffer engine` (the model Coffer's own engine runs on and its unattended passes).
- **Kind-agnostic / operational groups:** `coffer resource`, `coffer audit`, `coffer retention`, `coffer daemon` (including the `coffer daemon port show|set|clear` subgroup), `coffer open`.

Typical commands read as `coffer mcp add`, `coffer mcp tool enable/disable`, `coffer audit`, `coffer daemon start/stop/status`. The CLI is Coffer's primary interface for scripted workflows, dotfile-based setup, and remote (headless) machines where a browser is not available. Most read and list commands accept `--json` for machine-readable output; `coffer <group> <command> --help` says which.

**Which process.** A short-lived child process. The CLI is an independent Python process, installed on `PATH` as a console script entry point (`coffer`). It exits after executing one command. It does not stay running between invocations.

**Transport.** Loopback HTTP to `127.0.0.1:<port>/api/v1/`, using the token from `~/.coffer/daemon.json`. The CLI uses the detect-or-spawn pattern: if the daemon is not running when a CLI command is issued, the CLI spawns the daemon as a detached background process, waits for `daemon.json` to appear, and then connects. The user never sees "daemon not running" as an error; they may see a brief startup delay on first invocation.

`coffer daemon port` is the one exception to "every command calls the daemon": it reads and writes `~/.coffer/daemon-config.json` directly, with no daemon involved and none required. That is the point — the state the port setting most needs changing from is "no daemon is running", which is exactly what a route or a page could not serve.

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

## Web UI

**What it is.** The browser-based management interface. The Web UI provides a visual equivalent of every CLI management operation: registering MCP servers via JSON import, browsing server health and capability lists, toggling tools/resources/prompts on/off, reading the audit log and invocation history, and configuring retention policies. The information architecture reflects the resource-kind model, in three sidebar groups:

- **Agents** — `Agents` (the registry) and `Chat`, the two-column page onto the same conversations whichever surface opened them.
- **Resources** — one entry per resource kind that has a list UI: MCP servers, Skills, Knowledge, Memory, Model providers, Channels.
- **System** — `Activity`, `Sync`, `Settings`.

No "coming soon" placeholders appear — a kind only appears once it works, and none outlives its feature.

**Which process.** A browser process, served by the daemon. In production the daemon serves the built frontend itself, as static files at its own loopback origin — so the page and the API are same-origin. In development, a Vite dev server runs at `http://localhost:5173` and reaches the daemon across origins behind the `COFFER_DEV_CORS` opt-in. All data is fetched from the daemon's REST API. The **desktop shell** below is the second host for this same build.

**Transport.** Browser HTTP/REST to `http://127.0.0.1:<port>/api/v1/`, from a page loaded at `http://127.0.0.1:<port>/`.

**How the token reaches the page.** The daemon injects its live API token into the `index.html` it serves, as a `window.__COFFER_TOKEN__` global in the document head — on the bare `/` and on every client-side route served through the SPA fallback alike, `no-store` and without validators so a cached copy can never carry a restarted daemon's dead token. Any page the daemon serves is therefore authenticated by the act of being served; the token appears in no URL and in no browser storage. `coffer open` carries no credential — it reads the daemon's real port from `~/.coffer/daemon.json` and opens the browser there.

**Lifecycle.** The Web UI session is the lifetime of the browser tab. Closing the tab does not affect the daemon. The UI includes a daemon-offline banner that detects when the daemon is unreachable and displays the `coffer daemon start` command as a copyable affordance; the banner disappears automatically when the daemon comes back online.

**Security boundary.** `X-Coffer-Token` on every REST API call. CORS is same-origin by default; the Vite dev origins are added only under `COFFER_DEV_CORS`. Because the served page now carries the token, the daemon also refuses any request whose `Host` header is not a loopback authority, which is what closes DNS rebinding — a browser treats a rebound `evil.com` as same-origin, but still sends `Host: evil.com`. Because the daemon binds to loopback and the token is never transmitted to a remote origin, the trust model is equivalent to the CLI: local user account only.

---

## Desktop shell (`Coffer.app`)

**What it is.** A native host for the *same* web UI build — a macOS Tauri 2 application. It owns exactly four things a browser cannot do for itself: a window the OS treats as an application (Dock icon, Cmd-Tab entry), a resident tray with *Open Coffer* / *Sync* (badged when the vault needs attention) / *Restart daemon* / *Quit*, detect-or-spawn of the daemon at launch, and the credential handshake a locally-hosted page has no other way to make. It reimplements nothing the daemon already exposes over HTTP — folder picking, opening a file in an editor and revealing it in Finder are daemon routes a webview calls exactly as a browser tab does.

**Which process.** Its own OS process, with a webview inside it. The app is not served by the daemon; it *finds or starts* one. Closing the window hides to the tray rather than exiting.

**Transport.** The page is a **local asset** (`frontendDist: ../frontend/dist`), not a document fetched from the daemon — which is what makes it an application rather than a bookmarked browser window: the UI renders before the daemon answers, so an absent or wedged daemon produces a real screen with an actionable banner. API calls then go over loopback HTTP to `127.0.0.1:<port>/api/v1/`, with the port read from `~/.coffer/daemon.json`. Because nobody served that document, the daemon's injection cannot reach it; the shell supplies the same `window.__COFFER_BASE_URL__` / `window.__COFFER_TOKEN__` globals through an IPC command instead, alongside the first render and never before it.

**Lifecycle.** Started by the user (Dock, Spotlight, Cmd-Tab). Its daemon is resolved in a fixed order — a live daemon named by `daemon.json`, then the app's own bundle, then `~/.coffer/bin/`, then `PATH` — taking over a running daemon rather than spawning a second one. Quitting the app does not stop the daemon, and a restart from the tray or the offline banner is rate-limited against a tight spawn loop.

**Security boundary.** The same as the CLI: the token comes from `~/.coffer/daemon.json` (mode `0600`) and the daemon binds loopback. There is no rebinding exposure to close, because there is no attacker-controlled origin that can host the page — it is a file inside a signed-by-nobody-but-local app bundle.

---

## Surface comparison

| Surface        | Process type      | Transport to daemon        | Spawned by          | Lifecycle           |
| -------------- | ----------------- | -------------------------- | ------------------- | ------------------- |
| REST API       | Daemon            | — (is the daemon)          | System / manual     | Daemon lifetime     |
| MCP endpoint   | Daemon            | — (is the daemon)          | System / manual     | Daemon lifetime     |
| CLI (`coffer`) | Short-lived child | Loopback HTTP              | User / shell        | Per-command         |
| Stdio shim     | Per-session       | HTTP/SSE                   | MCP client          | MCP client session  |
| Web UI         | Browser tab       | Loopback HTTP (REST)       | `coffer open` / browser | Browser tab session |
| Desktop shell  | Native app + webview | Loopback HTTP (REST); local page | User (Dock / Spotlight) | Until quit from the tray |

---

**See also:** [Distribution](/architecture/distribution)
