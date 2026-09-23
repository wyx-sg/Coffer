# Security

::: warning Security invariants
These rules are non-negotiable and apply to the entire codebase. They are enforced by importlinter contracts, integration tests, and the architecture itself — not just by convention.

1. **Loopback-only binding.** The HTTP API binds exclusively to `127.0.0.1`. Any public-reachable surface runs as a separate process limited to signed callback paths — concretely, the SeaTalk callback listener (see [Channels & the public-reachable surface](#channels-the-public-reachable-surface)).
2. **Secret plaintext never persists.** Secrets are stored only as Fernet ciphertext in the `credentials` table; configuration stores credential _references_, not values. Plaintext exists in memory solely between decrypt and the spawn/header injection that consumes it — never in SQLite as plaintext, logs, audit, or any structured event. The Fernet master key is managed exclusively by `infrastructure/credentials/`, the only place permitted to import `keyring`.
3. **Token + CORS on the REST API.** Every management API call requires the `X-Coffer-Token` header. The daemon token lives in `~/.coffer/daemon.json` at mode `0600`.
4. **Outbound HTTP has real paths today, and exactly one of them is SSRF-guarded.** The daemon makes outbound calls now: provider introspection, remote speech-to-text, the internal engine's LLM calls, the Telegram and SeaTalk APIs, and `git` for sync. A guard exists — `infrastructure/net/ssrf_guard.check_url` — but it has exactly **one** caller, the provider introspector, so "every outbound URL passes through it" is not true and is not claimed. The constitution requires outbound HTTP to go through a guarded client; the open gap is the HTTP-transport MCP client, where the target host comes from user-registered config. See [Outbound HTTP](#outbound-http-one-guarded-path-and-the-rest). Public-reachable surfaces run as a separate process limited to signed callback paths.
   :::

## Threat model and trust boundaries

Coffer is a single-user, local-first tool. The trust model is correspondingly simple:

**Trusted**: the local user. Coffer assumes the person running the daemon is the owner of the machine. There is no multi-tenant model, no role-based access control, and no concept of an untrusted user sharing the same machine.

**Defended against**: two classes of attacker that exist even in a single-user local deployment:

1. **A stray local process.** Another process on the same machine — a malicious package installed in a project's `node_modules`, a browser extension with local HTTP access — could attempt to read Coffer's database, call its management API, or exfiltrate registered secrets. The loopback binding plus token authentication raises the bar: a process must guess or steal the 256-bit random token to call any mutating endpoint. The token is not in any environment variable; it lives only in `~/.coffer/daemon.json`, which has mode `0600` (readable only by the owner).

2. **A malicious upstream MCP server configuration.** A server registered with a carefully crafted `command` or `url` might attempt to reach internal network services (SSRF), exfiltrate credentials through environment variables, or write outside its working directory. The credential ref model (no literal secrets in config) and the static `env` reject-on-secret-regex check (which rejects any `env` value that looks like a token) are the current defences. Coffer *has* an SSRF guard, but it is wired into the provider introspector only — routing the HTTP-transport MCP client through it is still planned hardening. See [Outbound HTTP](#outbound-http-one-guarded-path-and-the-rest).

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

- **`~/.coffer/master.key`** — a `0600` file beside the database. This is the **default**: zero keychain prompts. (Why: macOS pins keychain ACLs to the binary's cdhash, so every rebuild of the unsigned daemon re-prompted for every secret. A file-backed master key removes the prompts entirely.)
- **The OS keychain** (service `coffer`, ref `master-key`) — opt-in hardening via **Settings → Security** or `coffer credentials storage --set keychain`. macOS may prompt once per daemon start. This is the mode that defends against offline exfiltration of `~/.coffer/`.

Resolution is **file-first**: the daemon looks for the file before the keychain. This makes relocation **crash-safe** — `relocate` moves only the master key and removes the old copy **last**, so an interrupted move always resolves back to a working state. The ciphertext in the `credentials` table is never touched by a relocation (the key moves; the data stays); switching storage modes does not re-encrypt.

A brand-new master key is generated **only when the `credentials` table is empty**. Ciphertext present with no resolvable key is a fatal, actionable startup error (`MasterKeyMissing`) — Coffer refuses to start rather than silently lose access to existing secrets.

::: warning Copy caveat
`coffer.db` contains ciphertext. Reading credentials out of a copied or synced vault requires the matching `master.key` file (or the keychain entry, in keychain mode). Keep the master key somewhere you can recover it, or a copied `coffer.db` yields no secrets.
:::

### Legacy keychain migration

Before envelope encryption, secrets lived directly in the OS keychain. On startup the daemon runs a one-time, best-effort migration: legacy keychain secrets whose refs are cited by registered resources are read, encrypted into the `credentials` table, and audited per ref as `credential_migrated`. If the keychain is locked, the migration is skipped and retried on the next startup.

::: warning Absolute constraint
`infrastructure/credentials/` is the **only** location in the entire codebase permitted to import `keyring`, and it does so only for the master key (keychain mode) and the legacy migration. This is enforced by an importlinter contract (Contract 4 in `backend/pyproject.toml`). Any PR that adds an `import keyring` anywhere else fails CI.
:::

The `StdioTransport` config schema has a second layer of defence: its `env` field runs a regex check on every static environment variable value and rejects any value that looks like a token or secret (matches the token-detection regex). This catches cases where a user accidentally pastes a secret literal into the static `env` map instead of using `credential_refs`.

## Channels & the public-reachable surface

The loopback-only invariant says a public-reachable surface runs as a separate process limited to signed callback paths. The **SeaTalk callback listener** is the concrete instantiation of that rule. SeaTalk delivers events only by public webhook, so it is the one place Coffer accepts inbound traffic that originated off the machine — and it does so through a process the daemon never lets the network reach.

- **Separate process, never the daemon.** The listener is a daemon-spawned child that runs only while a SeaTalk channel is enabled. It serves exactly one route, `POST /seatalk/{channel}`, on a loopback port (default `8787`, overridable via `COFFER_CALLBACK_PORT`). It holds no other state and can reach nothing but the daemon. The daemon itself stays loopback-only — it is never exposed.
- **Signature verification.** Every callback POST carries a `Signature` header that SeaTalk computes as `sha256(raw_body + signing_secret)` (lowercase hex). The listener recomputes the same digest from the raw body and the channel's signing secret and compares it in constant time (`hmac.compare_digest`). An empty secret or empty signature never verifies — an empty secret would collapse the MAC to `sha256(body)`, computable by anyone. The platform's `event_verification` challenge is answered inline; every other valid event is forwarded to the daemon over loopback carrying the daemon token.
- **The tunnel is the user's, the exposure is the listener's.** The user points a tunnel (cloudflared/ngrok) at the listener's loopback port. Only that one signed callback path is reachable from the internet; the management API and MCP endpoint are not on the tunnel at all.
- **Single-owner binding via pairing code.** A channel is bound to exactly one owner through an 8-character single-use pairing code (unambiguous alphabet, 1-hour TTL, bounded guesses, memory-only) issued from the UI/CLI and sent to the bot from the owner's account. Everyone else is ignored silently; re-pairing replaces the binding. There is no user-id-entry path — pairing also proves the transport round-trip.

Secrets reach the listener the same way upstream MCP subprocesses get theirs: the signing secrets, the daemon URL, and the daemon token are injected into the child's environment at spawn, never written to disk. The spawn is recorded in the upstream-pids directory so a daemon crash leaves nothing behind — the startup orphan sweep reaps it. A daemon-token rotation respawns the listener (the token is baked into the child's env).

## Sync security

Vault sync converges the vault **bidirectionally** with a git remote the user owns and configured. It is the one bounded exception to Local-First (constitution v0.6.0), and its security rests on what does and does not travel:

- **Network egress is real, and it is to a remote the user named.** A converge round runs `git` against that remote, fetching and pushing. There is no Coffer-operated endpoint involved, and the feature is **off until a remote is configured**.
- **The remote is a rendezvous, never a system of record.** Every machine's local vault stays complete, so the remote can be deleted and rebuilt from any one of them.
- **Ciphertext only.** Credentials travel as Fernet ciphertext blobs; what lands in the remote is undecryptable on its own.
- **The master key never travels with the data.** It is bootstrapped onto each machine **out-of-band**, via `coffer sync key export/import` — never committed.
- **`credentials_locked` until the key is present.** A machine that converged ciphertext but does not yet have the matching master key reports `credentials_locked` and refuses to spawn the affected resources. It never silently fails decryption.
- **An oversized deletion stops and asks.** A round applies a diff against the last state this vault provably held; when that diff would delete more than expected it is held (`sync_held_paths`) for the user to confirm or reject, and both answers are audited.

## Token authentication

At daemon startup, the daemon generates a 256-bit URL-safe random token (`secrets.token_urlsafe(32)`), writes `{"pid": ..., "port": ..., "token": "<token>"}` to `~/.coffer/daemon.json` with mode `0600`, and sets the active token via a FastAPI dependency (`require_token`) that is applied per-router.

Every route under `/api/v1/*` — including the MCP protocol endpoint at `/mcp` — requires this header. The `require_token` dependency rejects requests with a missing or incorrect token with HTTP 401. There is no fallback authentication method: no session cookie, no Basic auth, no API key with a different header name.

The token can be rotated via `POST /api/v1/daemon/rotate-token`. After rotation, the old token is immediately rejected and the new token is written to `daemon.json`. The rotation event is recorded in the audit log as `token_rotated`.

Clients (CLI, shim) all read the token from `daemon.json` before their first authenticated call. Because `daemon.json` is `0600`, only the process owner can read it — which is the entire access-control story for remote-process defence.

## CORS configuration

The daemon configures CORS to reject cross-origin requests from browser contexts. Because the HTTP API binds to loopback, the main risk is a malicious web page (open in a browser on the same machine) making requests to `http://127.0.0.1:<port>/api/v1/…` using the browser's `fetch()` API. CORS headers block this: only origins that match the configured allowlist are permitted to include credentials or read response bodies.

In production the daemon serves the built web UI itself, so the UI and the API share one origin and CORS is **same-origin by default**: the allowlist is empty and no cross-origin browser context is permitted. The Vite dev-server origins (`http://localhost:5173` and `http://127.0.0.1:5173`) are added only when `COFFER_DEV_CORS=1`, which is a frontend-development opt-in. The entire list can be overridden via `COFFER_CORS_ORIGINS`. Credentials are never allowed (`allow_credentials=False`) — auth is the `X-Coffer-Token` header alone. Origins not in the allowlist receive a CORS rejection from the browser before the token check even runs — defence in depth against the browser-based attack vector.

## Getting the token into the browser

The web UI is a browser page, so it needs the API token that the CLI and shim read straight out of `daemon.json`. Handing it over in a query string would be the obvious shortcut and is exactly what Coffer does **not** do: query strings and paths land in browser history, in the session-restore store, and in anything that syncs history across devices — which would undo Coffer's loopback-plus-token posture.

The daemon serves the page itself, so it hands the token over **in the response body** instead: the `index.html` it serves carries `window.__COFFER_TOKEN__` in its head, sourced from the same in-process token the header check compares against, so the injected value cannot drift from the accepted one. A body reaches neither history, nor the session-restore store, nor a screenshot, nor a pasted bug report, which is what made the URL unusable and makes this usable.

Two properties are load-bearing:

- **Every route that resolves to that document gets it** — the bare `/` and every client-side route served through the SPA fallback — so a bookmark, a typed address, a reload or a deep link is authenticated with no user action.
- **It is served `Cache-Control: no-store`, with no ETag and no Last-Modified.** The document now carries a per-daemon secret, and the daemon mints a new token on every start; a cached or revalidated copy would hand the browser a dead token. Hashed files under `/assets` keep normal caching. The page persists nothing, for the same reason.

`coffer open` therefore carries no credential. It reads the daemon's real port from `~/.coffer/daemon.json` (mode `0600`) and opens the browser there.

The desktop shell is the one host this mechanism does **not** reach: its page is a local asset nobody served, so there was no `index.html` to inject into. The shell hands the same globals to the page over IPC instead — a second supplier of the same credential, not a second way of authenticating.

## Host-header validation (DNS rebinding)

Binding to loopback stops a remote host from reaching the daemon. It does not stop a **browser**: a page on an attacker's origin whose hostname resolves to `127.0.0.1` is, as far as the browser is concerned, still same-origin with that attacker's origin — so CORS never applies and the page can read the response body. That bought nothing while the daemon's HTML held no secret; with the token in the document, a single `fetch("/")` would take the whole vault.

So the daemon refuses any request whose `Host` header is not a loopback authority — `127.0.0.1`, `localhost` or `::1`, with or without a port — answering `421` with error code `HOST_NOT_LOOPBACK`. Rebinding does not change the `Host` header: the browser sends the hostname from the URL it fetched, so a rebound request still names the attacker's own host and is refused before it reaches any route. `COFFER_ALLOWED_HOSTS` can add authorities; the backend test suite sets it because it drives the app in-process, and nothing in a real deployment needs it.

The check covers every surface on the daemon's port. It does not cover the separate `coffer-callback` listener, which is a different process on a different port — and the only thing a tunnel is ever pointed at. That listener authenticates inbound traffic by per-channel signature and forwards to the daemon over loopback, so public callbacks are unaffected.

## Outbound HTTP: one guarded path, and the rest

The daemon makes outbound calls today. Naming them precisely matters, because the guard's coverage is narrower than "outbound HTTP":

| Path                                        | Where                                       | Guarded?                                  |
| ------------------------------------------- | ------------------------------------------- | ----------------------------------------- |
| **Provider introspection** — asking a configured vendor endpoint what it offers | `infrastructure/provider/introspector.py` | **Yes.** The one caller of `check_url`.   |
| **Remote speech-to-text** for voice input   | `infrastructure/llm/transcription.py`       | No — the endpoint is a configured provider. |
| **The internal engine's LLM calls** (the curation and organise passes) | `infrastructure/llm/langchain_models.py` | No — same. |
| **The Telegram and SeaTalk APIs**           | `infrastructure/channel/`                   | No — fixed, well-known hosts.             |
| **HTTP-transport MCP servers**              | the MCP SDK's `create_mcp_http_client`      | No — and this is the gap that matters.    |
| **`git` fetch/push for vault sync**         | `infrastructure/sync/`                      | Not HTTP from Coffer's own client at all — a `git` subprocess against a remote the user configured. |

`infrastructure/net/ssrf_guard.check_url` rejects loopback, RFC 1918 private ranges and link-local addresses after DNS resolution. It is a real guard, and it is wired into exactly one call site. Anywhere the target host comes from *user-entered provider config*, the user entered it — so an unguarded call there is a user reaching their own endpoint, not an attacker pivoting.

The **HTTP-transport MCP client** is the open gap, and it is different in kind: its target also comes from user-registered config, but a server registration is the thing an attacker most plausibly gets to influence (a pasted `mcpServers` block from a README), and the MCP SDK's httpx client applies no IP-range filtering. Routing that client through the same guard is planned hardening, not yet shipped.

For stdio-transport MCP servers there is no outbound HTTP at all — the daemon spawns a subprocess and communicates over its stdin/stdout. The subprocess's environment is controlled (no secret literals) and its working directory is pinned by the `cwd` config field.
