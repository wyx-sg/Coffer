## Why

The daemon binds loopback only and every management call needs the token, but a browser can still reach `127.0.0.1` on a page's behalf. Two gaps were left open. The Host check accepted a loopback name on any port, and nothing looked at `Origin`. So a page on another site could send a request to `/mcp`, the event stream or any management route and have it reach the token check. The MCP specification requires an MCP server on HTTP to validate `Origin` on every connection. DNS rebinding against a loopback API with no Host or Origin check was the root cause of CVE-2025-49596 (MCP Inspector), CVE-2024-28224 (Ollama) and TS-2022-004/005 (Tailscale).

## What Changes

- One guard runs in front of everything the daemon's listener serves: the REST API, `/mcp`, the `/api/v1/events` stream, any websocket, and the served web UI.
- **Host:** the `Host` header must name `127.0.0.1`, `localhost` or `[::1]` with the port the request arrived on. Anything else, including a missing `Host` or a loopback name on another port, is refused with `403 HOST_NOT_ALLOWED`. This replaces the earlier `421 HOST_NOT_LOOPBACK`.
- **Origin:** a request that carries an `Origin` is refused with `403 ORIGIN_NOT_ALLOWED` unless the origin is one of Coffer's own:
  - the daemon's web origins on its port (`http://127.0.0.1:<port>`, `http://localhost:<port>`, `http://[::1]:<port>`);
  - the desktop app's origins (`tauri://localhost`, `http://tauri.localhost`);
  - with `COFFER_DEV_CORS=1`, the Vite dev origins `http://localhost:5173` and `http://127.0.0.1:5173`;
  - or exactly the list in `COFFER_CORS_ORIGINS`, which replaces the desktop and dev entries.
- A request with no `Origin` goes on to the usual token check. This covers the CLI, the shim, agents' MCP clients and curl.
- Each distinct refused value is logged once. The number of values remembered is capped.
- CORS reads the same cross-origin list, so the two cannot disagree. There is still no wildcard and no credentials.

## Capabilities

### New Capabilities

### Modified Capabilities
- `daemon`: the loopback Host requirement becomes a Host-and-Origin requirement, with scenarios for a foreign origin on every surface, for Coffer's own origins and no-Origin clients, and for the development opt-in.

## Impact

- Backend: `surfaces/http/host_guard.py`, `surfaces/http/cors.py`, `surfaces/http/errors.py`, `surfaces/http/middleware.py`.
- Frontend: locale strings for the two error codes and the generated backend-keys fixture.
- Docs: the security architecture page, the web UI guide, the configuration, error-code and REST references, the observability page, and the daemon auth and origin guard ADR.
