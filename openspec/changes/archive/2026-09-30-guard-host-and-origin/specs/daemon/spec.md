## RENAMED Requirements

- FROM: `### Requirement: Refuse a request whose Host is not loopback`
- TO: `### Requirement: Refuse a request whose Host or Origin is not the daemon's own`

## MODIFIED Requirements

### Requirement: Refuse a request whose Host or Origin is not the daemon's own
The daemon MUST check two headers on every request it answers before any route sees the request. This covers the management API, the `/mcp` endpoint, the `/api/v1/events` stream, any websocket, the status probe and the served web UI. It applies to every listener the daemon opens.

- **Host.** The daemon MUST refuse a request whose `Host` header does not name `127.0.0.1`, `localhost` or `[::1]` together with the port the request arrived on. It answers `403` with error code `HOST_NOT_ALLOWED`. A missing `Host` is refused. A `Host` with no port means port 80. Binding to loopback (see "Bind every endpoint to loopback only") stops a remote host. It does not stop a **browser** on a page whose hostname an attacker re-resolves to `127.0.0.1`. That is DNS rebinding: the browser treats the page as same-origin, so CORS does not apply. Rebinding does not change the `Host` header, so the request still names the attacker's hostname and is refused before it can read a token out of the served document. This check is what makes "Hand the browser its token in the served page" safe.
- **Origin.** The daemon MUST refuse a request that carries an `Origin` header unless that origin is one of Coffer's own, answering `403` with error code `ORIGIN_NOT_ALLOWED`. Coffer's own origins are:
  - the daemon's web origins on the port the request arrived on: `http://127.0.0.1:<port>`, `http://localhost:<port>` and `http://[::1]:<port>`;
  - the desktop app's origins, `tauri://localhost` and `http://tauri.localhost`;
  - the Vite dev origins `http://localhost:5173` and `http://127.0.0.1:5173`, only when `COFFER_DEV_CORS=1` is set;
  - when `COFFER_CORS_ORIGINS` is set, exactly the origins it lists, in place of the desktop and dev entries.
- **No Origin.** A request with no `Origin` header MUST go on to the ordinary token check. This is how the CLI, the shim, agents' MCP clients and `curl` send requests.
- **CORS.** CORS MUST grant only these origins. It never grants a wildcard and never allows credentials.
- **Logging.** Each distinct refused value is logged once.

See [Daemon Auth and Origin Guard](../../../docs/decisions/daemon-auth-and-origin-guard.md).

#### Scenario: a rebound page is refused before it can read the token
- **GIVEN** a page on an attacker-controlled origin whose hostname resolves to `127.0.0.1`, which the browser therefore treats as same-origin with the daemon,
- **WHEN** it fetches any daemon URL, including `/`, so that the request carries `Host: evil.example:<port>`,
- **THEN** the daemon refuses the request with `403 HOST_NOT_ALLOWED` and the body carries no token,
- **AND** a request that names a loopback address on another port is refused the same way, while the same request addressed to `127.0.0.1:<port>`, `localhost:<port>` or `[::1]:<port>` is served normally.

#### Scenario: a request from a page on another site is refused on every surface
- **GIVEN** a running daemon with no development opt-in,
- **WHEN** a request carrying `Origin: https://evil.example`, the Vite origin, a loopback origin on another port, or `Origin: null` reaches a management route, `/mcp`, `/api/v1/events`, the status probe, the served page, or a CORS preflight, even with the right `Host` and a valid token,
- **THEN** the daemon answers `403 ORIGIN_NOT_ALLOWED` without running the route, and grants no `Access-Control-Allow-Origin`.

#### Scenario: Coffer's own pages and clients that send no Origin are let through
- **GIVEN** a running daemon on `<port>`,
- **WHEN** a request arrives with no `Origin`, or with `Origin` set to `http://127.0.0.1:<port>`, `http://localhost:<port>`, `http://[::1]:<port>`, `tauri://localhost` or `http://tauri.localhost`,
- **THEN** the guard lets it through: the status probe answers, and a management route, `/mcp` and `/api/v1/events` answer with their own token check,
- **AND** the desktop app's preflight is granted its origin.

#### Scenario: a development origin is let through only when opted in
- **GIVEN** a daemon started without `COFFER_DEV_CORS` or `COFFER_CORS_ORIGINS`,
- **WHEN** a request carries `Origin: http://localhost:5173`,
- **THEN** it is refused with `403 ORIGIN_NOT_ALLOWED`,
- **AND** with `COFFER_DEV_CORS=1` the same request is let through while a foreign origin is still refused,
- **AND** with `COFFER_CORS_ORIGINS=http://localhost:5174` only the listed origin and the daemon's own origins are let through.
