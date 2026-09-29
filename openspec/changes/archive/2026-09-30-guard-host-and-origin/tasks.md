## 1. Guard

- [x] 1.1 Host check requires a loopback name and the port the request arrived on; refusal is `403 HOST_NOT_ALLOWED`
- [x] 1.2 Origin check: the daemon's own web origins plus `cors.cross_origin_allowlist()` (desktop app always, dev origins behind `COFFER_DEV_CORS` / `COFFER_CORS_ORIGINS`); no `Origin` passes; refusal is `403 ORIGIN_NOT_ALLOWED`
- [x] 1.3 Websocket handshakes are closed with 1008 before accept
- [x] 1.4 Each distinct refused value is logged once, with a cap on how many are remembered
- [x] 1.5 CORS and the guard read one cross-origin list

## 2. Tests

- [x] 2.1 Rebinding (`Host: evil.example:8000`) and loopback on another port are refused, including for `/`
- [x] 2.2 A foreign origin is refused on REST, `/mcp`, `/api/v1/events`, the status probe, the served page and preflights
- [x] 2.3 The daemon's own origins, the desktop origins and no-Origin requests reach the token check
- [x] 2.4 A dev origin passes only with `COFFER_DEV_CORS=1` or when `COFFER_CORS_ORIGINS` lists it
- [x] 2.5 The e2e and visual suites still pass (spare ports with `COFFER_CORS_ORIGINS`)

## 3. Docs

- [x] 3.1 Security architecture page: the principle, and how to allow a development origin
- [x] 3.2 Web UI guide, configuration, error-code and REST references, observability page, ADR
- [x] 3.3 Error codes in both locales and the backend-keys fixture
