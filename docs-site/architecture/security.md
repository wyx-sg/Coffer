---
title: Security model
description: Coffer's threat model and the mechanisms behind it — loopback binding and the Host and Origin checks, the per-start API token, the envelope-encrypted credential store, the SSRF guard, agent identity, channel owner pairing, what reaches logs and audit, and how sync carries secrets.
---

# Security model

This page states what Coffer defends against and what it does not, then walks through each mechanism that holds the line: the network boundary, API authentication, the credential store, outbound requests, agent identity, messaging channels, logging, and sync. It is for engineers reviewing Coffer's security posture and for anyone deciding whether to trust it with their API keys.

## Threat model

Coffer is a **single-user tool on one machine**. There is one owner, no accounts, no roles and no multi-tenancy. The daemon runs as you, and so does everything it starts.

### What Coffer defends against

| Threat | Defence |
| --- | --- |
| A host on the network reaching the daemon. | The daemon binds `127.0.0.1` only. The OS refuses remote connections before they reach Coffer. |
| A web page in your browser reaching the daemon — including through DNS rebinding. | Every request whose `Host` is not the daemon's own loopback address and port is refused, and so is every request whose `Origin` is not one of Coffer's own. Every management call must also carry the API token. |
| Another user account on the same machine. | `daemon.json`, `daemon-config.json` and `master.key` are mode `0600`. |
| Secrets leaking through ordinary artefacts: config files, logs, the audit trail, the sync remote, screenshots of a URL. | Secrets exist at rest only as Fernet ciphertext. Configs hold refs. Audit records refs, never values. Sync carries ciphertext only, and only when you opt in. The token is never put in a URL. |
| An offline copy of `~/.coffer/` (a stolen backup, a synced folder). | Only in keychain mode: the master key then lives in the OS keychain, so the copied database is ciphertext without its key. |
| A stranger messaging your Telegram or SeaTalk bot. | A channel obeys exactly one paired owner, bound by a single-use pairing code. Everyone else is ignored. |
| A provider base URL pointed at an internal address. | The provider introspector resolves the host and refuses loopback, private, link-local and similar ranges. |

### What Coffer does not defend against

Stated plainly, so nobody over-trusts the defaults:

- **Processes running as you.** Anything that can read `~/.coffer/daemon.json` has the API token, and the API can return any stored secret (`GET /api/v1/credentials/{ref}`). In the default key mode, anything that can read `~/.coffer/` also has the master key beside the ciphertext. Local-user isolation is the operating system's job.
- **The agents themselves.** Chat turns run Claude Code with `bypassPermissions` and Codex with `approvalPolicy = "never"` and `sandbox = "danger-full-access"`. Coffer does not gate individual tool calls: the paired owner issuing the instruction is the human in the loop. An agent can do anything you can do in its working directory.
- **Upstream MCP servers you register.** A stdio server is a program Coffer starts as you, with the environment you configured. Registering a server is trusting it.
- **Agent identity spoofing.** The shim reports which agent it serves; nothing verifies it cryptographically (see [Agent identity](#agent-identity)).
- **A compromised OS keychain, or a malicious Coffer binary.**

### Trust boundaries

```mermaid
flowchart LR
  subgraph net["Network"]
    REMOTE["Remote hosts"]
    WEBPAGE["Web pages"]
  end
  subgraph user["Your user account"]
    AGENTS["Agents and shim"]
    CLIENTS["CLI, web UI, desktop"]
    DJ["daemon.json 0600"]
    subgraph daemon["coffer-daemon on 127.0.0.1"]
      GUARD["Host and Origin checks, token"]
      CORE["Services"]
      STORE[("Ciphertext store")]
    end
    KEY["master.key or keychain"]
  end
  subgraph ext["Outbound only"]
    PROV["Model providers"]
    IM["Telegram and SeaTalk"]
    GIT["Your git remote"]
  end
  REMOTE -.->|"refused by loopback bind"| GUARD
  WEBPAGE -.->|"refused by Host and Origin checks"| GUARD
  CLIENTS -->|token from| DJ
  AGENTS -->|token from| DJ
  CLIENTS --> GUARD
  AGENTS --> GUARD
  GUARD --> CORE
  CORE --> STORE
  KEY --> CORE
  CORE --> PROV
  CORE --> IM
  CORE -->|"ciphertext only"| GIT
```

## Loopback binding

The daemon binds `127.0.0.1` and nothing else ([`infrastructure/daemon/port_alloc.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/daemon/port_alloc.py)). Uvicorn is handed the pre-bound socket rather than a host and port, so nothing downstream can widen the bind. It is the only socket Coffer listens on: Telegram is long-polled from inside the daemon, and each SeaTalk channel holds one outbound websocket connection. No channel needs a public URL, a tunnel or an inbound port.

## The Host and Origin checks

Binding to loopback stops remote hosts. It does not stop a browser, because any page you have open can send requests to `127.0.0.1`. Coffer runs two checks on every request before any route sees it. They cover the REST API, the `/mcp` endpoint, the `/api/v1/events` stream, websockets, the status probe and the served web UI. The daemon has one listener and every surface is on it, so there is no path that skips the checks. This follows the MCP specification, which says an HTTP server must validate `Origin` on every connection. The same gap caused CVE-2025-49596 in the MCP Inspector, CVE-2024-28224 in Ollama and TS-2022-004/005 in Tailscale.

### Host: DNS rebinding

Suppose an attacker controls `evil.example` and re-points its DNS name at `127.0.0.1`. To the browser, the page is still same-origin with `evil.example`, so CORS never applies and the page can read the response body. The daemon puts its API token into the web UI's `index.html` (see below), so one `fetch("/")` from that page would take the whole vault.

DNS rebinding does not change the `Host` header. A rebound request still says `Host: evil.example:8000`. So the daemon accepts a request only when `Host` names `127.0.0.1`, `localhost` or `[::1]` **and** the port the request arrived on. It refuses anything else, including a request with no `Host` and a loopback name on another port:

```text
HTTP/1.1 403 Forbidden
{"error": {"code": "HOST_NOT_ALLOWED", "message": "Coffer only answers requests addressed to 127.0.0.1:8000 or localhost:8000; this one named evil.example:8000.", "details": null}}
```

### Origin: requests from other sites

A page on another site can still *send* a request to the right address even though it cannot read the answer: a form post, an `EventSource`, or a `fetch` in `no-cors` mode. The token already makes such a request fail. The Origin check makes it fail without relying on the token. A request that carries an `Origin` header gets through only if the origin is one of Coffer's own:

| Origin | When it is allowed |
| --- | --- |
| `http://127.0.0.1:<port>`, `http://localhost:<port>`, `http://[::1]:<port>` | Always. This is the web UI the daemon serves, opened in a browser tab. |
| `tauri://localhost`, `http://tauri.localhost` | By default. This is the desktop app, which loads the UI from its own origin. |
| `http://localhost:5173`, `http://127.0.0.1:5173` | Only with `COFFER_DEV_CORS=1`. This is the Vite dev server. |
| Any origin listed in `COFFER_CORS_ORIGINS` | Only when that variable is set. The list replaces the desktop and Vite entries. |

Every other origin, including `null`, gets `403 ORIGIN_NOT_ALLOWED`. The check happens before the route runs, so it applies even when the request carries the right token.

A request with **no** `Origin` goes on to the token check. That is how the CLI, the shim, an agent's MCP client and `curl` send requests. Browsers are the only clients that send `Origin`, and a non-browser client can put whatever it likes there anyway.

The daemon logs each distinct refused `Host` or `Origin` once, as `http.request_refused`. A page that retries in a loop cannot flood the log.

### Allowing a development origin

You only need this when you serve the UI yourself instead of opening it from the daemon or the desktop app.

- **The Vite dev server on port 5173.** Start the daemon with `COFFER_DEV_CORS=1`. `make dev` does this for you.
- **Any other origin**, such as Vite on a spare port: set `COFFER_CORS_ORIGINS` to a comma-separated list of exact origins before you start the daemon, for example `COFFER_CORS_ORIGINS=http://localhost:5174,http://127.0.0.1:5174`. The list replaces the desktop and Vite entries, so include those too if you still need them. The daemon's own origins are always allowed.

Both variables are read when the daemon starts, so restart it after you change them. Never put a site you do not control on the list: any page on a listed origin can call the daemon.

`COFFER_ALLOWED_HOSTS` (comma-separated hostnames, or `*`) adds names that the Host check accepts. It never relaxes the Origin check. The backend test suite sets it because it drives the app in-process with made-up hostnames. A real installation does not need it.

## The API token

### Minting and storage

At every start the daemon mints a fresh token with `secrets.token_urlsafe(32)` (256 bits) and writes it into `~/.coffer/daemon.json` along with the pid and port. The file is staged with `mkstemp` and moved into place atomically, so it never exists with a mode wider than `0600`. The token is not persisted across restarts, not placed in any environment variable, and not written into any agent's config: the shim reads it from `daemon.json` at runtime.

### Checking it

Every route under `/api/v1/*` and the `/mcp` endpoint require an `X-Coffer-Token` header, compared in constant time (`hmac.compare_digest`) against the daemon's in-process token. A missing or wrong token is `401`; a request that arrives before the daemon has published its token is `503`. The one unauthenticated API route is `GET /api/v1/daemon/status`, the readiness probe the CLI and shim call before they have a token; it returns lifecycle phase, version, executable, port, release channel, feature switches, machine name and an aggregate upstream health summary — nothing secret.

`coffer daemon rotate-token` (or `POST /api/v1/daemon/rotate-token`) mints a new token, rewrites `daemon.json`, invalidates the old token immediately, and records `token_rotated` in the audit log.

### Getting it into the page

The web UI needs the token too, and a URL is the wrong channel: it ends up in browser history, session restore, screenshots and pasted bug reports. So the daemon hands it over in the **response body**. Whenever it serves `index.html` — for `/` and for every client-side route through the SPA fallback — it injects `window.__COFFER_TOKEN__` as the first script in `<head>`, read from the same in-process variable the token check compares against, so what the page holds cannot drift from what the API accepts ([`webui.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/surfaces/http/webui.py)).

- The document is served `Cache-Control: no-store`, with no ETag or Last-Modified, so a restarted daemon's browser never gets the previous daemon's token from a cache. Hashed files under `/assets` keep normal caching.
- The page persists nothing: reload after a daemon restart and it is authenticated against the new daemon.
- `coffer open` carries no credential. It reads the daemon's port from `daemon.json` and opens the browser there.

The token in the page is exactly what makes the [Host check](#host-dns-rebinding) mandatory; neither exists without the other.

The desktop shell loads the same frontend as a local asset that nobody served, so there is no `index.html` to inject into. It supplies the same two globals over a Tauri IPC command before first render instead. The Vite dev server does the same from `daemon.json` during development. Each host is a credential *supplier*; the page reads one pair of globals either way.

### CORS

CORS grants exactly the cross-origin entries of the [Origin table](#origin-requests-from-other-sites): the desktop app's origins by default, and the development origins when you opt in. The browser-served UI is same-origin with the API and needs no CORS. CORS never uses a wildcard, and `allow_credentials` is always false, so no cookie is ever attached. CORS and the Origin check read the same list, so they cannot disagree.

## The credential store

### Envelope encryption

Secrets live only as **Fernet ciphertext** in the `credentials` table of `~/.coffer/coffer.db`, keyed by a **ref** — a name such as `github-token`. Everything else in Coffer holds refs:

- An MCP server's config maps environment variables or headers to refs in `transport.credential_refs`. Its schema rejects a static `env` or header value that looks like a secret (`Bearer …`, `ghp_…`, `github_pat_…`, `sk-…`, `xox?-…`, a JWT prefix) and tells you to move it into `credential_refs`.
- A channel's bot token or app secret, a provider's API key, and the sync remote's push credential are refs.
- When you switch an agent onto a provider, the agent is pointed at the [local model proxy](/architecture/model-proxy) on loopback and authenticates with its own local proxy token (`coffer proxy token --agent-uid <uid>`, run by Claude Code's `apiKeyHelper` and Codex's provider `auth` command). The provider's key is never written into an agent's file or environment, and no route or command returns it: the daemon decrypts it and hands it to the proxy, which injects it upstream and holds it in memory only.

Plaintext exists in memory only between decrypt and the spawn or header injection that consumes it. Registration probes every cited ref before writing the resource, so a missing secret fails with `CREDENTIAL_MISSING` and leaves nothing behind; deleting a credential that a resource still cites is refused with `409`; and deleting a resource releases any credential no remaining resource cites.

The daemon is the only owner of secret material. The CLI and the web UI store and read secrets through `/api/v1/credentials`; an import contract forbids the CLI from importing the credential module at all, so each machine has exactly one reader of the key.

**The daemon is the sole credential-store owner.** Every surface — web UI, CLI, shim — reaches secrets through the daemon's `/api/v1/credentials` routes and toggles master-key storage via `/api/v1/settings/credentials`; the CLI never touches the store in-process (an importlinter contract forbids the CLI from reaching the keychain) (ADR envelope-encrypted-credential-store).

### The master key

The one secret outside the database is the Fernet master key, managed by [`MasterKeyManager`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/credentials/master_key.py). It lives in exactly one of two places:

| Mode | Where | Defends against an offline copy of `~/.coffer/`? | Prompts |
| --- | --- | --- | --- |
| `file` (default) | `~/.coffer/master.key`, mode `0600` | No — the key sits beside the ciphertext. | None. |
| `keychain` | OS keychain, service `coffer`, ref `master-key` | Yes. | At most once per daemon start on macOS. |

Switch with **Settings → Security** or `coffer config set credentials.storage keychain`. Switching **moves the key, never re-encrypts the data**; the old copy is deleted last, and resolution is file-first, so an interrupted move always resolves to a working key.

Startup is fail-closed. The daemon counts `credentials` rows *before* resolving the key, and creates a new key only when the table is empty. Ciphertext with no resolvable key stops the daemon with `MASTER_KEY_MISSING`, naming the path; a locked keychain that might hold the key stops it with `CREDENTIAL_LOCKED` rather than creating a second key that would shadow it.

`keyring` is imported by exactly one module, [`infrastructure/credentials/keyring_adapter.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/credentials/keyring_adapter.py), and an import contract fails the build if surfaces or application code import it.

::: warning The macOS keychain and unsigned builds
macOS pins a keychain item's access list to the code signature of the binary that created it. Coffer's binaries are not signed with an Apple Developer Team ID, so each new build looks like a different application to the keychain. That is why the default keeps the master key in a file: with one key per vault instead of one keychain item per secret, keychain mode costs at most one prompt per daemon start rather than one per secret on every rebuild. Only a stable Team ID signature would remove the prompt entirely.
:::

::: tip Back up the key with the database
A copy of `coffer.db` without its master key yields no secrets. Back up `~/.coffer/` as a whole, or export the key with `coffer sync key export` and keep it somewhere safe.
:::

## Outbound requests

[`infrastructure/net/ssrf_guard.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/net/ssrf_guard.py) resolves a URL's host and refuses it if any resolved address is loopback, private (RFC 1918, `fc00::/7`), link-local, carrier-grade NAT (`100.64.0.0/10`), multicast, unspecified or reserved. A name that fails to resolve counts as blocked.

The rule ([Principles → Network defaults](/architecture/principles)) is that a URL Coffer probes or fetches on your behalf from something typed into a form passes the guard, while an endpoint you configure as your own does not. Today one adapter fetches from typed input: the provider introspector ([`infrastructure/provider/introspector.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/provider/introspector.py)), behind the three probes a connection editor runs before anything is saved — `POST /api/v1/models/list-models`, `/test-connection` and `/detect-protocol`. Each checks the base URL before its first request. Two cases skip the check:

- A connection whose protocol is local by design (`ollama`) is never checked, since its URL is loopback.
- `detect-protocol` classifies a loopback host (`localhost`, `127.0.0.1`, `::1`, `0.0.0.0`, `host.docker.internal`) as `ollama` without sending any request.

So a probe of a non-Ollama endpoint on a private or link-local address is refused. Saving and using a connection are not probes, and the guard is not applied to the endpoints you configure as your own:

- **HTTP-transport MCP servers**, whose URL you registered — they commonly run on your own machine or network.
- **Coffer's own model calls** and **transcription**, which go to the providers you configured.
- **Telegram and SeaTalk**, the IM platforms' own hosts, including the media URLs they hand back.
- **Vault sync**, which is a `git` subprocess against the remote you configured.

The guard resolves DNS at validation time and the HTTP client resolves again when it connects, so a host that re-points between the two can slip past. Pinning the resolved address through to the client would break TLS certificate verification; for a single-user daemon where you typed the URL yourself, that residual risk is accepted.

## Agent identity

When Coffer installs its MCP entry into an agent, it writes `coffer-mcp-shim --agent-uid <uid>`. The shim stamps that uid onto the MCP handshake as `_meta["coffer/agent-uid"]`, and the gateway uses it for two things:

1. **Reach.** Every scoped resource is filtered with `is_active(scope, agent_uid)`. A session with no identity — a shim you configured by hand — matches only unscoped resources, so it sees strictly less, never more. An older shim sending a name-based key is read as unidentified; there is no fallback that could match a stale label against a scope.
2. **Attribution.** Every builtin tool call carries an `agent` argument naming the caller, which tools such as `coffer__write` record. The gateway **always** sets it from the handshake identity (resolved to the agent's current name): a value the client supplied is dropped unconditionally, and with no identity the argument is simply absent. No builtin tool advertises the argument, so a model has nothing to fill in.

The identity is self-reported by a process running as you. It is not a security boundary against a malicious local process — any such process already holds the token — and the spec says so rather than implying stronger isolation.

## Channels and owner pairing

A channel is the one surface through which someone outside your machine can make an agent act, so it has exactly one gate: **owner pairing**.

- You issue a pairing code from the channel's page or with `coffer channel`. A code is 8 characters from an alphabet without look-alikes (no `0`, `O`, `1`, `I`), single-use, valid for one hour, allows 10 wrong guesses before it is invalidated, and lives only in memory — a daemon restart drops it.
- You send the code to the bot from your own account (or tap the start link that carries it). That binds your platform identity as the channel's owner and records `channel_paired` in the audit log.
- From then on the channel obeys only messages whose sender is the owner. In a group, a message addressed to the bot by anyone else gets a one-line refusal; in a paired chat, a message from a different member is ignored silently and cannot re-pair the channel; an unpaired direct chat can do nothing but present a pairing code. When a sender's identity cannot be established in a group, the message is refused, never assumed to be the owner's.
- A channel's **inverted scope** limits which agents it may drive at all, and a channel whose scope is empty does not start.

Channel secrets are refs, resolved from the credential store when the adapter starts.

## What goes into logs and audit

- **Logs** (`~/.coffer/logs/`, one JSON object per line) record events, identifiers and errors. No code path logs a secret value, a token or a decrypted credential.
- **Audit** records every lifecycle change with its actor. Credential events (`credential_set`, `credential_read`, `credential_deleted`, `credential_migrated`) record the **ref** only. Resource configs pass through the kind's `audit_redactor` first — the MCP kind strips `transport.env` and `transport.headers` entirely — so a value pasted into the wrong field still does not reach `audit_log`. Master-key events (`master_key_relocated`, `master_key_exported`, `master_key_imported`) record that the event happened, not the key.
- **The sync history** stores the remote's commit and errors after the push credential has been redacted out.

## Sync carries ciphertext only

Vault sync converges the vault with a git remote you own. It is off until you configure a remote, and its security rests on what does and does not travel:

- **Credentials travel only if you opt in** (`coffer sync remote set --with-credentials`), and then only as Fernet ciphertext, one `credentials/<ref>.enc` file per secret. What lands in the repository cannot be decrypted on its own.
- **The master key never travels with the data.** You carry it between machines yourself: `coffer sync key export` writes it out on one machine, `coffer sync key import` installs it on another, and `coffer sync key fingerprint` lets you compare the two. Importing a different key first backs the existing one up to a timestamped `master.key.bak-*` file, because it may be the only key that decrypts existing ciphertext.
- **A machine without the matching key** reports the refs it holds ciphertext for but cannot decrypt, rather than failing silently.
- **Reach does not travel.** Which resources are enabled, and for which agents, is decided on each machine, so another machine's round can never widen what this one exposes.
- **Deletions are guarded.** A round that would delete more than its configured share holds for your confirmation.

See [Vault sync](/architecture/vault-sync) for the full protocol.

## Trade-offs and alternatives

- **Keychain as the default secret store.** Rejected: under an unsigned, frequently rebuilt binary, macOS re-prompted for every secret on every rebuild. File-default with a keychain opt-in removes the prompts while still offering the stronger mode.
- **A passphrase-derived key.** Rejected for the default: a prompt at every daemon start, and a forgotten passphrase loses every secret.
- **Persisting the API token across restarts.** Rejected: a long-lived on-disk token that unlocks the credential endpoints is worse than a per-process one.
- **Putting the token in the URL.** Rejected: URLs leak into history, screenshots and bug reports; a response body does not.
- **Relying on loopback binding alone.** Rejected: that is exactly the gap DNS rebinding walks through.
- **Per-tool approval prompts for agents.** Not built: every instruction already comes from the paired owner, so a per-tool prompt would only re-confirm what the owner asked for.

## Where it lives in the code

| Path | Contents |
| --- | --- |
| [`surfaces/http/auth.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/surfaces/http/auth.py) | Token check. |
| [`surfaces/http/host_guard.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/surfaces/http/host_guard.py) | `Host` and `Origin` checks. |
| [`surfaces/http/cors.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/surfaces/http/cors.py), [`middleware.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/surfaces/http/middleware.py) | CORS allowlist and middleware order. |
| [`surfaces/http/webui.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/surfaces/http/webui.py) | Serving the UI with the injected token. |
| [`infrastructure/daemon/bootstrap.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/daemon/bootstrap.py), [`atomic_write.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/daemon/atomic_write.py) | Token minting, `daemon.json`, `0600` writes. |
| [`infrastructure/credentials/`](https://github.com/wyx-sg/Coffer/tree/main/backend/coffer/infrastructure/credentials) | Encrypted store, master key, keyring adapter. |
| [`infrastructure/net/ssrf_guard.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/net/ssrf_guard.py) | SSRF guard. |
| [`application/mcp/gateway_parsing.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/application/mcp/gateway_parsing.py), [`gateway_builtin.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/application/mcp/gateway_builtin.py) | Handshake identity and the `agent` argument overwrite. |
| [`application/channel/pairing.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/application/channel/pairing.py), [`inbound.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/application/channel/inbound.py) | Pairing codes and the owner gate. |

## Related

- [Credentials guide](/guides/credentials)
- [Security policy](/contributing/security) — how to report a vulnerability.
- [Envelope-Encrypted Credential Store](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/envelope-encrypted-credential-store.md)
- [A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-auth-and-origin-guard.md)
- [Per-Agent Resource Scope](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/per-agent-resource-scope.md)
- [Managed Agents Run With Full Permissions; Owner Pairing Is the Gate](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/managed-agents-run-with-full-permissions.md)
- Specs: [credentials](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/credentials/spec.md), [daemon](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/daemon/spec.md), [channels](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/channels/spec.md)
