# A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard

**Status**: Accepted
**Date**: 2026-09-13
**Deciders**: Yuxing Wu
**Related**: [Detect-or-Spawn](daemon-detect-or-spawn.md), [Daemon Binds a Fixed Port](daemon-binds-a-fixed-port.md), [Desktop Shell Over a Shared Frontend](desktop-shell-over-a-shared-frontend.md), [stdio Shim Bridge](stdio-shim-bridge.md), spec daemon "Require a token on every management call", spec daemon "Answer the status probe without a token", spec daemon "Rotate the token from REST or the command line", spec daemon "Hand the browser its token in the served page", spec daemon "Refuse a request whose Host is not loopback", spec daemon "Serve the built web UI from the daemon's own origin", spec desktop-app "Supply the page its daemon connection over IPC", PR #342, PR #376

## Context

The daemon holds the user's MCP servers, decrypted credentials on demand, the
agents' configuration and memory. It binds `127.0.0.1` only (spec daemon "Bind
every endpoint to loopback only"), which keeps other machines out but not other
things on this machine: another local user, and — the harder case — any web
page the user has open, since a browser will send requests to `127.0.0.1` on a
page's behalf.

Its clients reach it in three different ways:

- **the CLI and the shim** are processes running as the user and can read a
  file in `~/.coffer/`;
- **a browser tab** loads the UI the daemon itself serves at
  `http://127.0.0.1:<port>/` and can read nothing from disk;
- **the desktop shell** loads the same UI build as a bundled asset, so its page
  origin is `tauri://localhost` on macOS (`http://tauri.localhost` elsewhere),
  and its API calls to `http://127.0.0.1:<port>` are cross-origin.

The browser case is where the design has moved. The browser's only way to get
the token used to be a one-time `#code=…` fragment that `coffer open` put in
the launch URL; the page exchanged it at `POST /daemon/web-session` and kept the
token in `localStorage`. That worked once per `coffer open`. Every other way of
arriving — a bookmark, a typed address, a reload, a tab restored after sleep —
re-read the stored token, which after any daemon restart was dead, and every
call returned 401. The UI called it a connectivity problem and advised a
refresh, which re-read the same dead token. The design's own premise ("the URL
is the only channel a freshly opened browser will read") was wrong: the daemon
serves the page, so the response body is a channel too.

## Options Considered

### Option A — Per-start token in a header; the document's host supplies it; a loopback `Host` guard (chosen)

- The daemon mints `secrets.token_urlsafe(32)` at every start, never persisted
  across restarts, and publishes it only in `~/.coffer/daemon.json` (mode
  `0600`). Every management call and `/mcp` carries it as `X-Coffer-Token`;
  `require_token` compares it in constant time and answers 401
  (`surfaces/http/auth.py`). `GET /api/v1/daemon/status` is the one
  unauthenticated route, because it is the readiness probe clients call before
  they can have read the token, and it carries no secrets.
- Whoever hosts the document supplies the page two globals,
  `window.__COFFER_TOKEN__` and (when the API is not same-origin)
  `window.__COFFER_BASE_URL__`, and the frontend reads only those
  (`frontend/src/lib/auth.ts`). The daemon injects the token into every
  `index.html` it serves — `/` and every client-side route — as a script in the
  head, sourced per request from the same in-process variable `require_token`
  checks, and serves that document `Cache-Control: no-store` with no ETag or
  Last-Modified (`surfaces/http/webui.py`). The desktop shell answers an IPC
  command, `get_daemon_info` (`desktop/src/daemon.rs`), with base URL and token
  read from `daemon.json`, and the page sets the globals before first render.
  The Vite dev server's plugin injects both globals from `daemon.json`
  (`frontend/vite.config.ts`).
- Every request whose `Host` header is not a loopback authority (`127.0.0.1`,
  `localhost`, `::1`, with or without a port) is refused with
  `421 HOST_NOT_LOOPBACK` (`surfaces/http/host_guard.py`), before CORS and
  before any route.
- CORS allows only the desktop shell's origins by default, adds the Vite
  origins under `COFFER_DEV_CORS=1`, and never allows credentials
  (`surfaces/http/cors.py`).

Pros: nothing about the session is persisted in the browser — no token in
storage, a URL, or history — and a restarted daemon's page recovers on reload,
deep links included. One token and one header serve every client. Cons: the
`Host` check becomes load-bearing for every surface on the port; the served
HTML must never be cached. Wins because it is the only option that is both
self-healing across restarts and leaves no credential anywhere a URL or
storage would.

### Option B — One-time code in the launch URL, token kept in `localStorage`

The design this replaced, built and removed in PR #342 along with its
`web_session` store, `POST /daemon/web-code`, `POST /daemon/web-session` and the
`coffer.token` storage key. Pros: the long-lived token never appears in a URL;
the code is single-use. Cons: authenticates only a tab opened by `coffer open`;
the stored token dies with the daemon that minted it, so every restart strands
every bookmark and reload behind 401 with no recovery but re-running
`coffer open`. Fixing only the error copy would explain the dead end more
politely without removing it. Loses.

### Option C — An `HttpOnly`, `SameSite=Strict` session cookie

The daemon sets a cookie when it serves the page; the browser sends it on API
calls. Pros: script on the page cannot read the credential; cookies are the
browser's native mechanism. Cons: the desktop shell's page is on another origin
(`tauri://localhost`), so the cookie is third-party there and needs
`SameSite=None` plus `allow_credentials`, which reopens CSRF that a header-only
token never had; the CLI and shim would still need the header, so there would be
two credential mechanisms; cookies are keyed by host and not by port, so any
other service on `127.0.0.1` would receive it; the cookie would still have to be
minted per start and so buys nothing over injection for restarts. Loses on the
two-mechanism cost and the cross-origin shell.

### Option D — No authentication on loopback

Pros: nothing to hand anyone. Cons: loopback is not a boundary against the
browser — any web page can send requests to `127.0.0.1`, and a "simple" POST
needs no preflight — nor against other local users. With credentials and agent
configuration behind the API that is not acceptable. Loses.

### Option E — Persist one long-lived token across restarts

Pros: the stored-token bug disappears; the page could keep it. Cons: a
long-lived on-disk token that unlocks the credential endpoints is a worse trade
than a per-process one, and a token that never changes cannot be revoked by
restarting. Loses.

### Option F — Put the token in the URL directly (query or fragment)

Pros: simplest to open. Cons: a URL reaches browser history, the session-restore
store, history sync across devices, terminal scrollback, screenshots and pasted
bug reports. The response body reaches none of those. Loses.

### Option G — Let the browser read the token file, or rely on CORS as the boundary

A page cannot read `~/.coffer/daemon.json` at all, so the first half is not a
mechanism. Treating CORS as the boundary fails because CORS governs whether a
page may *read* a cross-origin response, not whether the request is sent, and
it does not apply at all to a DNS-rebound page, which the browser considers
same-origin. Coffer's CORS allowlist is therefore a convenience for the shell
and dev server, not a security control. Loses as a boundary.

### Option H — Loopback binding alone, no `Host` check

Pros: less code. Cons: DNS rebinding — a page on `evil.com` whose hostname the
attacker re-resolves to `127.0.0.1` is, to the browser, same-origin with
`evil.com`, so it can read response bodies. Once the served `index.html` carries
the token, one `fetch("/")` would hand over the vault. Rebinding does not change
the `Host` header, so the check refuses it. The injection in Option A does not
ship without this guard. Loses.

## Decision

The token is minted per start, lives only in the `0600` `daemon.json` and in
process memory, and travels only in the `X-Coffer-Token` header. The UI gets it
from whoever hosts its document — the daemon by injection, the desktop shell
over IPC, the Vite dev server by its plugin — and never persists it. Every
request must name a loopback `Host` or is refused with 421. CORS admits the
shell's own origins and nothing else by default, with credentials off.

Rules a future change must respect:

- The injected value and the accepted value come from the same variable
  (`auth.get_active_token`), read per request, so a rotation
  (`POST /api/v1/daemon/rotate-token` or `coffer daemon rotate-token`) cannot
  make them disagree.
- Any document carrying the token is `no-store` with no validators. A cached or
  revalidated copy would hand a restarted daemon's browser the previous
  daemon's token.
- The SPA fallback must not answer the daemon's own roots (`api`, `mcp`,
  `health`, `docs`, `redoc`, `openapi.json`), matched by whole path segment:
  a prefix test such as `startswith("mcp")` would claim the UI's `/mcp-servers`
  route.
- The middleware order is fixed (`surfaces/http/middleware.py`): trace
  outermost, then the host guard, then CORS, so a rebound request is refused
  before CORS can bless it and the refusal still carries a trace id.
- A new host for the UI is a new *supplier* of the two globals, not a new code
  path in the frontend.

## Consequences

- Restart the daemon and reload the page, even on a deep link, and it is
  authenticated against the new daemon. `coffer open` carries no credential; it
  reads the port from `daemon.json` (spawning a daemon if needed) and opens the
  browser at that origin.
- The fixed port ([Daemon Binds a Fixed Port](daemon-binds-a-fixed-port.md))
  and the injected token together make a bookmark a complete way in: the
  address does not move and the page does not need anything stored.
- The daemon's loopback socket is the only socket Coffer listens on, so the host
  guard covers every surface there is. A future listener on the same port
  inherits it; one on a different port must bring its own.
- `COFFER_ALLOWED_HOSTS` (comma-separated, or `*`) widens the guard. The backend
  test suite sets `*` because it drives the ASGI app in-process; nothing in a
  real deployment needs it.
- Allowing `tauri://localhost` widens nothing that matters: any Tauri app on the
  machine shares that origin, but it would still need the token, and any process
  running as the user can already read `daemon.json`. Whether the macOS WebView
  enforces CORS for a custom-scheme page was not measured; the entry is harmless
  if it does not and required if it does.
- A page left open across a token rotation or a daemon restart holds a dead
  token until it is reloaded (browser) or re-handshakes (the shell does this
  after its own restart). Clients that read `daemon.json` — CLI, shim — pick up
  the new token themselves ([stdio Shim Bridge](stdio-shim-bridge.md)).
- Identity inside the token is not per-agent: any holder of the token is the
  user. Per-agent scoping on `/mcp` uses a self-reported agent uid, a documented
  trust boundary under this single-user loopback posture (spec mcp-gateway
  "Take the agent identity from the handshake").
