## 1. Proxy process

- [x] 1.1 Relay (byte pass-through, open-list headers, key injection, commit point, failover, usage tee)
- [x] 1.2 ASGI surface (routes, Host/Origin refusal, token auth, control routes)
- [x] 1.3 Spool writer, entry (`coffer-daemon proxy`), `proxy.json`
- [x] 1.4 Supervisor (attach, spawn, drain, restart, push state)

## 2. Daemon side

- [x] 2.1 Per-agent tokens in the credential store; sync skips them
- [x] 2.2 Proxy state from connections, agents and tokens
- [x] 2.3 Projection through the proxy for Claude Code and Codex
- [x] 2.4 `coffer proxy token|rotate|status` and `/api/v1/proxy/*`
- [x] 2.5 Remove `coffer provider key` and the key routes; no key injection into Codex

## 3. Local connections

- [x] 3.1 `local_runtime` on the connection, loopback-only, key optional
- [x] 3.2 Read-only detection with minimum versions; `detect-local`, `add --local`

## 4. Tests and docs

- [x] 4.1 Relay, failover, auth, Host/Origin, rotation and supervisor tests with fake upstreams
- [x] 4.2 Projection tests on a fake HOME
- [x] 4.3 Architecture page, providers guide, security page, principles, references
