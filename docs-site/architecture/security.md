# Security

::: warning Security invariants
These rules are non-negotiable and apply to the entire codebase. They are enforced by importlinter contracts, integration tests, and the architecture itself — not just by convention.

1. **Loopback-only binding.** The HTTP API binds exclusively to `127.0.0.1`. Any public-reachable surface (if ever introduced) runs as a separate process limited to signed callback paths.
2. **Secret plaintext never persists.** Secrets are stored only as Fernet ciphertext in the `credentials` table; configuration stores credential _references_, not values. Plaintext exists in memory solely between decrypt and the spawn/header injection that consumes it — never in SQLite as plaintext, logs, audit, or any structured event. The Fernet master key is managed exclusively by `infrastructure/credentials/`, the only place permitted to import `keyring`.
3. **Token + CORS on the REST API.** Every management API call requires the `X-Coffer-Token` header. The daemon token lives in `~/.coffer/daemon.json` at mode `0600`.
4. **Outbound HTTP will be SSRF-guarded when introduced.** The constitution requires that outbound HTTP calls — when the daemon makes them (e.g., to HTTP-transport MCP servers) — go through a SSRF-guarded client. This is a forward-looking invariant: the current implementation uses the MCP SDK's httpx client with no IP filtering. A hardened SSRF-guarded wrapper is planned. Public-reachable surfaces, when introduced, run as a separate process limited to signed callback paths.
   :::

## Threat model and trust boundaries

Coffer is a single-user, local-first tool. The trust model is correspondingly simple:

**Trusted**: the local user. Coffer assumes the person running the daemon is the owner of the machine. There is no multi-tenant model, no role-based access control, and no concept of an untrusted user sharing the same machine.

**Defended against**: two classes of attacker that exist even in a single-user local deployment:

1. **A stray local process.** Another process on the same machine — a malicious package installed in a project's `node_modules`, a browser extension with local HTTP access — could attempt to read Coffer's database, call its management API, or exfiltrate registered secrets. The loopback binding plus token authentication raises the bar: a process must guess or steal the 256-bit random token to call any mutating endpoint. The token is not in any environment variable; it lives only in `~/.coffer/daemon.json`, which has mode `0600` (readable only by the owner).

2. **A malicious upstream MCP server configuration.** A server registered with a carefully crafted `command` or `url` might attempt to reach internal network services (SSRF), exfiltrate credentials through environment variables, or write outside its working directory. The credential ref model (no literal secrets in config) and the static `env` reject-on-secret-regex check (which rejects any `env` value that looks like a token) are the current defences. A SSRF-guarded outbound HTTP client is a planned hardening per the constitution's invariant.

What Coffer does **not** defend against (in the default configuration): a privileged attacker who can read `~/.coffer/` directly, or a malicious Coffer binary. In the default mode the master key sits in a `0600` file beside the encrypted database — the same `~/.coffer/` boundary that already excluded a reader of that directory — so envelope encryption does not change this line. The opt-in **keychain mode** raises it: with the master key in the OS keychain, the ciphertext in `~/.coffer/coffer.db` is useless to an attacker who exfiltrates the directory's contents without also unlocking the keychain. A compromised OS keychain (in keychain mode) and a malicious Coffer binary remain out of scope for a local-first developer tool.

## Loopback-only HTTP binding

The daemon's FastAPI application binds its HTTP server to `127.0.0.1`, not `0.0.0.0`. This is a constitutional requirement, not a configuration option.

The practical effect: no request originating outside the local machine can reach the management API or the MCP protocol endpoint. A remote attacker who cannot first compromise the machine has no network path to Coffer. This makes the daemon safe to run persistently without a firewall rule — the OS rejects out-of-machine connections before they reach the application.

The one intentional unauthenticated endpoint is `GET /api/v1/daemon/status`. It is loopback-only and returns only lifecycle phase, version, port, and an aggregate upstream health summary — no secrets, no per-resource details, no audit data. It exists to let the CLI and the shim probe for daemon readiness before they have read the token from `daemon.json`.

## Credentials: the encrypted store

Secrets are stored as **Fernet ciphertext** in the `credentials` table of `~/.coffer/coffer.db` (envelope encryption). The plaintext value lives only in memory, between decrypt and the spawn/header injection that consumes it. The mechanism:

1. **Store**: the user calls `POST /api/v1/credentials` with a ref and a secret value. The daemon Fernet-encrypts the value with the master key and writes only the ciphertext into the `credentials` table, recording a `credential_set` audit event (no secret value in the details). The plaintext is never written anywhere on disk.
2. **Reference**: when registering an MCP server, the user specifies `credential_refs: { "SOME_ENV_VAR": "my-secret-ref" }` in the config. This mapping — from env var name to a ref into the encrypted credential store — is stored in `config_json` in the database. The secret itself is not.
3. **Materialise**: at upstream-spawn time, the daemon reads the ciphertext for each `credential_refs` entry, decrypts it with the master key, injects the plaintext into the subprocess environment (or request headers, for HTTP transport), and then spawns the process. The plaintext is in memory only for the duration of the spawn call; it is never written to a log, an audit entry, or a database column.
4. **Delete**: the user calls `DELETE /api/v1/credentials/{ref}`. The daemon removes the row and records a `credential_deleted` audit event (without the secret value in the details).

### The master key

Envelope encryption means there is exactly one piece of secret material outside the database: the Fernet **master key**. It lives in **exactly one** of two places:

- **`~/.coffer/master.key`** — a `0600` file beside the database. This is the **default**: zero keychain prompts. (Why: macOS pins keychain ACLs to the binary's cdhash, so every rebuild of the unsigned daemon re-prompted for every secret. A file-backed master key removes the prompts entirely. See [ADR-015](/reference/decisions/ADR-015-envelope-encrypted-credential-store).)
- **The OS keychain** (service `coffer`, ref `master-key`) — opt-in hardening via **Settings → Security** or `coffer credentials storage --set keychain`. macOS may prompt once per daemon start. This is the mode that defends against offline exfiltration of `~/.coffer/`.

Resolution is **file-first**: the daemon looks for the file before the keychain. This makes relocation **crash-safe** — `relocate` moves only the master key and removes the old copy **last**, so an interrupted move always resolves back to a working state. The ciphertext in the `credentials` table is never touched by a relocation (the key moves; the data stays); switching storage modes does not re-encrypt.

A brand-new master key is generated **only when the `credentials` table is empty**. Ciphertext present with no resolvable key is a fatal, actionable startup error (`MasterKeyMissing`) — Coffer refuses to start rather than silently lose access to existing secrets.

::: warning Backup caveat
`coffer.db` now contains ciphertext. Restoring a backup of it requires the matching `master.key` file (or the keychain entry, in keychain mode). Back up the master key alongside the database, or a restored `coffer.db` is unreadable.
:::

### Legacy keychain migration

Before envelope encryption, secrets lived directly in the OS keychain. On startup the daemon runs a one-time, best-effort migration: legacy keychain secrets whose refs are cited by registered resources are read, encrypted into the `credentials` table, and audited per ref as `credential_migrated`. If the keychain is locked, the migration is skipped and retried on the next startup.

::: warning Absolute constraint
`infrastructure/credentials/` is the **only** location in the entire codebase permitted to import `keyring`, and it does so only for the master key (keychain mode) and the legacy migration. This is enforced by an importlinter contract (Contract 4 in `backend/pyproject.toml`). Any PR that adds an `import keyring` anywhere else fails CI.
:::

The `StdioTransport` config schema has a second layer of defence: its `env` field runs a regex check on every static environment variable value and rejects any value that looks like a token or secret (matches the token-detection regex). This catches cases where a user accidentally pastes a secret literal into the static `env` map instead of using `credential_refs`.

## Token authentication

At daemon startup, the daemon generates a 256-bit URL-safe random token (`secrets.token_urlsafe(32)`), writes `{"pid": ..., "port": ..., "token": "<token>"}` to `~/.coffer/daemon.json` with mode `0600`, and sets the active token via a FastAPI dependency (`require_token`) that is applied per-router.

Every route under `/api/v1/*` — including the MCP protocol endpoint at `/mcp` — requires this header. The `require_token` dependency rejects requests with a missing or incorrect token with HTTP 401. There is no fallback authentication method: no session cookie, no Basic auth, no API key with a different header name.

The token can be rotated via `POST /api/v1/daemon/rotate-token`. After rotation, the old token is immediately rejected and the new token is written to `daemon.json`. The rotation event is recorded in the audit log as `token_rotated`.

Clients (CLI, shim, desktop shell) all read the token from `daemon.json` before their first authenticated call. Because `daemon.json` is `0600`, only the process owner can read it — which is the entire access-control story for remote-process defence.

## CORS configuration

The daemon configures CORS to reject cross-origin requests from browser contexts. Because the HTTP API binds to loopback, the main risk is a malicious web page (open in a browser on the same machine) making requests to `http://127.0.0.1:<port>/api/v1/…` using the browser's `fetch()` API. CORS headers block this: only origins that match the configured allowlist are permitted to include credentials or read response bodies.

In production, the allowed origins are the Tauri desktop shell's `tauri://localhost` and `http://tauri.localhost`. The Vite dev-server origins (`http://localhost:5173` and `http://127.0.0.1:5173`) are added only when `COFFER_DEV_CORS=1`. The entire list can be overridden via `COFFER_CORS_ORIGINS`. Credentials are never allowed (`allow_credentials=False`) — auth is the `X-Coffer-Token` header alone. Origins not in the allowlist receive a CORS rejection from the browser before the token check even runs — defence in depth against the browser-based attack vector.

## Outbound HTTP: current state and planned hardening

When the daemon connects to an HTTP-transport MCP server, it currently uses the MCP SDK's `create_mcp_http_client` (backed by `httpx`) with no IP-range filtering. There is no SSRF guard in place today.

The constitution states this as a forward-looking invariant: outbound HTTP calls, **when introduced**, must go through a SSRF-guarded client. Implementing that guard — rejecting connections to loopback, RFC 1918 private ranges, and link-local addresses after DNS resolution — is planned hardening, not yet shipped.

For stdio-transport servers, there is no outbound HTTP at all — the daemon spawns a subprocess and communicates over the process's stdin/stdout. The subprocess's environment is controlled (no secret literals) and its working directory is pinned by the `cwd` config field.

## See also

- [Constitution reference](/reference/project/constitution) — Local-First, Credentials, and Network defaults invariants
- [Architecture reference](/reference/project/architecture) — Cross-cutting concerns table and the credentials module location
