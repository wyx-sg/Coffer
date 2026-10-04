---
title: Security model
description: Coffer's threat model and the mechanisms behind it — the secret boundary against a prompt-injected agent (plaintext only to a present human in the desktop app, approval before a secret goes somewhere new), what stays exposed, loopback binding and the Host and Origin checks, the per-start API token, the envelope-encrypted secret store and the master key, the SSRF guard, agent identity, channel owner pairing, what reaches logs and audit, and how sync carries secrets.
---

# Security model

This page states what Coffer defends against and what it does not, then walks through each mechanism that holds the line: the secret boundary, the network boundary, API authentication, the secret store and its master key, outbound requests, agent identity, messaging channels, logging, and sync. It is for engineers reviewing Coffer's security posture and for anyone deciding whether to trust it with their API keys. For day-to-day use of the boundary — `coffer run`, approvals, key backups — see [Secrets](/guides/secrets).

## Threat model

Coffer is a **single-user tool on one machine**. There is one owner, no accounts, no roles and no multi-tenancy. The daemon runs as you, and so does everything it starts — including the coding agents it serves.

### The adversary

The case that matters is a **prompt-injected agent running as you**: Claude Code or Codex read a hostile web page, issue, README or tool result, and now follows the attacker's instructions with your shell. It can run any command you can, read `~/.coffer/daemon.json` and call every management route with its token, run every `coffer` command, write its own configuration, and read the initial environment of any process you own. Coffer cannot take any of that away from it, and does not try to.

Second in line is **a web page in your browser**, which can send requests to `127.0.0.1` and, through DNS rebinding, read the answers.

Out of scope: a malicious program you installed yourself (nothing at user level stops that), and another user account on the machine (loopback binding and file modes keep that one out).

### The boundary is the secret

Because an agent can already do almost anything you can, Coffer does not gate *configuration*: agents may read and change Coffer's setup through the CLI, the REST API and MCP, exactly as you can. That is how an agent sets Coffer up for you. Coffer instead guards the two things an agent **cannot** do on its own:

1. **Learn a secret's plaintext.** No route, command or MCP tool returns a stored value or the master key. Plaintext reaches only a person present at the desktop app, after a presence check for that one operation. See [Plaintext reaches only a present human](#plaintext-reaches-only-a-present-human).
2. **Make Coffer send a secret somewhere new.** A secret does not have to be read to be stolen: an agent could register an MCP server whose environment cites your GitHub token and whose command is the attacker's script, and let Coffer deliver the token. So a secret goes to a new destination only after you approve it in the desktop app. See [A secret goes somewhere new only with your approval](#a-secret-goes-somewhere-new-only-with-your-approval).

Three rules keep those two honest:

3. **The protections are switched off only the same way** — by an approval in the desktop app. No environment variable, config key or CLI flag does it.
4. **Every listener checks `Host` and `Origin`**, which closes the browser vector. See [The Host and Origin checks](#the-host-and-origin-checks).
5. **Agents get capabilities, not keys.** The MCP gateway injects an HTTP upstream's headers itself, so an agent sees tool results and never the token.

This is the same pair of moves password managers and agent vendors settled on: a human-presence gate the agent cannot satisfy, and a broker that injects the secret so the agent never holds it.

::: danger The boundary holds only in a signed release
The presence grant that proves "a person approved this" is signed with a key derived from the master key, and only the signed desktop app can read that key — **once Coffer ships binaries signed with an Apple Developer ID**. It does not yet. Until then every build is a development build: the master key is the file `~/.coffer/master.key`, any process running as you can read it, and so a same-user process can forge a grant. **In a development build the secret boundary does not hold.** See [Development builds](#development-builds).
:::

### What Coffer defends against

| Threat | Defence |
| --- | --- |
| An agent asking Coffer for a secret's value — through REST, the CLI, MCP, or a master key export. | No route, command or tool returns a value or the key. Reveals and key backups exist only in the desktop app, behind a presence check. |
| An agent making Coffer deliver an existing secret to a program or URL of its choosing. | Every destination is checked at the moment of use. A secret goes to a target no person approved only after an approval in the desktop app, signed with a presence grant. |
| An agent switching the protection off. | It waits for an approval in the desktop app. |
| A secret pasted into a skill file, `.env` or script that syncs to git, or echoed into a transcript. | Standalone secrets are cited as `coffer://secret/<name>` and resolved by `coffer run` into one child's environment only, with exact values masked in its output. This guards against accidents, not against the agent (see below). |
| A web page in your browser reaching the daemon — including through DNS rebinding. | Every request whose `Host` is not the daemon's own loopback address and port is refused, and so is every request whose `Origin` is not one of Coffer's own. Every management call must also carry the API token. The browser UI offers no reveal, backup or approval. |
| A host on the network reaching the daemon. | The daemon binds `127.0.0.1` only. The OS refuses remote connections before they reach Coffer. |
| Another user account on the same machine. | `daemon.json`, `daemon-config.json` and, in a development build, `master.key` are mode `0600`. |
| Secrets leaking through ordinary artefacts: config files, logs, the audit trail, the sync remote, screenshots of a URL. | Secrets exist at rest only as Fernet ciphertext. Configs hold refs. Audit records refs, never values. Sync carries ciphertext only, and only when you opt in. The token is never put in a URL. |
| An offline copy of `~/.coffer/` (a stolen backup, a synced folder). | In a signed release the master key is in the Keychain, not in `~/.coffer/`, so the copy is ciphertext without its key. In a development build, only in keychain mode. |
| A stranger messaging your Telegram or SeaTalk bot. | A channel obeys exactly one paired owner, bound by a single-use pairing code. Everyone else is ignored. |
| A provider base URL pointed at an internal address. | The provider introspector resolves the host and refuses loopback, private, link-local and similar ranges. |

### What stays exposed

Stated plainly, so nobody over-trusts the boundary. Each is a consequence of running as the same user, and the UI labels the secrets they cover as readable by local processes rather than describing Coffer as protecting them.

- **A stdio MCP server's environment.** A third-party server that takes its token from an environment variable holds it in its initial environment, which any process running as you can read with `ps eww` — measured from inside Claude Code's sandbox too, and against a hardened-runtime binary. Coffer cannot fix a server it did not write. It marks such servers "readable by other processes on this Mac"; prefer an HTTP server with gateway-injected headers wherever the upstream offers one.
- **`coffer run` children.** A standalone secret resolved into a command's environment is readable by the agent that started the command: the agent is the parent, and `ps eww` works regardless. It can also simply run `coffer run --secret X -- env`. `coffer run` is an accident guard, and every standalone secret is listed as readable by local processes.
- **Computer-use agents.** An agent granted Accessibility or screen control can click an approval or type your password. The presence check holds against an agent with a shell, not one with the mouse.
- **The signed CLI shares the key's access group.** In a signed release the `coffer` CLI could read the master key. That is acceptable because no CLI code path returns plaintext, the key or a grant, and the hardened runtime keeps other processes from attaching to or injecting into Coffer's signed binaries.
- **Bypass modes.** An agent in `bypassPermissions`, `--yolo` or `danger-full-access` has no sandbox of its own. Nothing above depends on one; nothing above protects what such an agent reaches outside Coffer either. Coffer's own chat turns run agents this way (below).
- **Development builds.** Everything in [Development builds](#development-builds).

And, as before:

- **The agents' own actions.** Chat turns run Claude Code with `bypassPermissions` and Codex with `approvalPolicy = "never"` and `sandbox = "danger-full-access"`. Coffer does not gate individual tool calls: the paired owner issuing the instruction is the human in the loop. An agent can do anything you can do in its working directory.
- **Upstream MCP servers you register.** A stdio server is a program Coffer starts as you. Registering a server is trusting it.
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
    CLIENTS["CLI and web UI"]
    DJ["daemon.json 0600"]
    subgraph daemon["coffer-daemon on 127.0.0.1"]
      GUARD["Host and Origin checks, token"]
      CORE["Services"]
      GATE["Secret boundary: grants and approvals"]
      STORE[("Ciphertext store")]
    end
    APP["Desktop app: presence check, signs grants"]
    KEY["Master key: Keychain access group (signed) or master.key (development)"]
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
  CLIENTS -->|"config, writes, no plaintext"| GUARD
  AGENTS -->|"config, writes, no plaintext"| GUARD
  APP -->|"signed grant"| GUARD
  GUARD --> CORE
  CORE --> GATE
  GATE --> STORE
  KEY --> CORE
  KEY --> APP
  GATE -->|"approved targets only"| PROV
  GATE -->|"approved targets only"| IM
  GATE -->|"ciphertext, approved URL"| GIT
```

## Plaintext reaches only a present human

Three operations let plaintext out, and all three live only in the desktop app: **revealing or copying a secret**, **writing a master key backup**, and **approving** an [approval](#a-secret-goes-somewhere-new-only-with-your-approval). Each runs the same way:

1. **A presence check first.** The app runs a LocalAuthentication check — Touch ID, or your login password — with a fresh context for this one operation and **no reuse window**: the next reveal asks again. The prompt macOS shows names the operation and its target ("reveal the secret github/token"), so it is the operating system, not the page, that tells you what you are approving. Cancelling sends nothing.
2. **A one-time challenge.** The app asks the daemon for a challenge bound to that operation and that target — this ref, this approval, this folder. A challenge expires within two minutes and is consumed by its first use, whether or not it verifies.
3. **A signed grant.** The app signs the challenge with a key derived from the master key, which only Coffer's signed binaries can read. The derived key is computed when needed and never stored.
4. **The operation.** The daemon checks the signature and acts only if it verifies — releasing the one value to the app's window, writing the backup into the folder you picked, or applying the approval. A grant for one operation authorises nothing else, and a missing, reused, expired or forged grant is refused with `PRESENCE_GRANT_INVALID`.

A process an agent controls cannot read the master key in a signed release, so it cannot sign a grant. The daemon releases a value to the app rather than letting the app decrypt ciphertext itself: there is one decryption path, and the app needs no access to the store.

Around the three operations:

- **No other path returns plaintext.** There is no plaintext read route; `coffer secret list` shows names only. There is no key export command or route. The browser UI shows **Open in Coffer app** where these actions would be. The one other place plaintext leaves the daemon is `coffer run`'s resolve of standalone secrets, which is confined to the `secret/` namespace and covered under [What stays exposed](#what-stays-exposed).
- **The master key never crosses the API.** A key backup is written by the daemon into the folder you chose, as `coffer-master-key.cfk`, mode `0600`, never over an existing file; the response carries only the path and the fingerprint. The file holds the key encrypted under a key scrypt derives from a passphrase you type in the app (at least eight characters), so a copy that lands somewhere shared opens nothing without it. The passphrase goes from the page to the shell to the daemon's request and is never stored, logged or audited; validation failures are logged without the submitted values for the same reason.
- **Every release is audited:** a reveal as `secret_revealed` with the ref only, a backup as `master_key_exported`, an approval as `secret_approval_approved`.
- **Writing stays open.** Any surface may store a secret, a new standalone one (`secret/<name>`) or a new value for one already in use: whoever supplies a value already has it. A write is audited with its actor and whether it replaced a value, never with the value. What a write cannot do is send the secret somewhere new: a destination is checked at the moment of use.

## A secret goes somewhere new only with your approval

A **destination** is a place Coffer sends a secret's plaintext. Each one has a **target**: what actually receives the value, written so a person can judge it.

| Destination | Target |
| --- | --- |
| A stdio MCP server's environment variable | the full command line, its working directory and its non-secret environment — `NODE_OPTIONS=--require …` changes what the process does |
| An HTTP MCP server's header | the server's URL |
| A Telegram channel's bot token | the Telegram bot |
| A SeaTalk channel's app secret | the SeaTalk app id |
| The sync remote's push token | the git URL |

A provider connection's key goes through the same check against its base URL and the protocol that presents it: the local model proxy and Coffer's own engine receive it only for an approved URL. A custom-tool group's authentication is checked against its base URL like an HTTP MCP server's header; a new destination type joins this list in the change that introduces it.

The boundary is applied twice. When a resource is registered or its configuration changes, one seam every kind goes through (an MCP server, a channel, a provider connection, and the sync remote when it is set) evaluates the destination at once: a supplied value is approved, and a ref in use elsewhere or a target that moved records its pending approval in the same call, so it is on the approvals list and shown where you saved it. And every consumer asks the boundary before it resolves a secret, at the moment of use — spawning a server, starting a channel adapter, pushing a sync round. A secret approved for its current target is injected. Otherwise nothing is injected, the attempt fails with `SECRET_BINDING_PENDING`, and one pending approval is recorded per target; a newer target supersedes the approval for an older one. Because the check happens at use, a change made behind Coffer's back — a vault file edited by hand, a server another machine synced in — is caught where it matters.

Two things approve a binding without a person:

- **A value supplied for it.** When a destination is registered or changed, a ref that has never been sent anywhere, is not a standalone secret and was written on this machine within the last five minutes is approved with that registration. Every "add" flow stores the pasted secret and then registers what cites it, and the binding is recorded in that call, so a second destination citing the same ref waits, however soon it comes. A secret already sent elsewhere, kept for `coffer run`, or met only at the moment of use is never counted as supplied.
- **The protection switched off**, which itself waits for an approval.

One more change widens where a secret goes and waits for the same approval:

- **Switching the protection off** (`secrets.require_approval`). Switching it on applies at once.

Approving takes a presence grant. Rejecting does not — refusing only narrows what Coffer does — and works from every surface. The desktop app raises a notification for each new pending approval and opens a sheet to answer it; a command whose change leaves a secret waiting prints `waiting for approval in the Coffer app` and exits `9`. Several approvals can be answered under one presence check: the grant is signed over a digest of exactly the approvals and targets you were shown, so it approves that list and nothing else, and any item whose target changed since is skipped (see [Secrets → Answering several at once](/guides/secrets#answering-several-at-once)). See [Secrets → Approvals](/guides/secrets#approvals).

### Placement is part of the approval {#placement}

A binding is pinned to more than its target. It is keyed by the secret's ref, the destination and the **slot** — the header an HTTP MCP server or custom-tool group carries it in, the environment variable of a stdio server — so moving an approved secret to another header or variable of the same server, or the same ref into a second server, is a new binding that waits for a person exactly as a changed URL does. A provider key's target also names the protocol (`model api <base URL> as openai`), because the protocol decides whether the key rides in `Authorization` or `x-api-key`. The only places a stored secret is ever written into a request are the headers a destination's definition names. An argument hole in a custom tool's path, query, headers or body is filled only from what the calling agent passes, never from the secret store; a tool header spelled like the secret header cannot replace the injected value; and a secret is never put in a URL or a body.

### A redirect never carries a secret {#redirects}

Approving a secret for a URL approves that origin, not wherever the server says to go next. `httpx` strips only `Authorization` from a request when a redirect crosses origins; `X-API-Key`, `api-key` and a key in a query would follow, and the OpenAI and Anthropic SDKs build clients that follow redirects by default. So one rule holds on every path that injects a secret: **it does not follow a redirect to another origin.** The clients Coffer builds for the engine, the provider probe, the model proxy, custom-tool requests and channel platforms do not follow redirects at all (the answer is the 3xx, reported as "not followed"; the one exception is a SeaTalk media download, whose short-lived `Authorization` bearer the client already drops on a cross-origin hop); the MCP SDK's HTTP transport follows only within the endpoint's own origin; and the git credential helper behind vault sync answers only for the origin of the remote the call is about, so a remote that redirects to another host is never offered the token. A test makes each path send a canary secret to an origin that redirects to a second one and checks what the second receives, and another scans the code for a client built to follow.

The boundary's state is machine-local: its bindings, pending approvals, switches and the time each ref was first stored here are JSON files under `~/.coffer/local/secret-boundary/`, written atomically, never committed to the vault and never synced. A pending replacement value waits there as ciphertext.

## Development builds

The boundary rests on one fact: in a signed release, only Coffer's signed binaries can read the master key, so only the desktop app can sign a grant. Coffer does not ship such binaries yet, and a build from source never will. In those **development builds**:

- the master key is the file `~/.coffer/master.key` (or, opt-in, a login-keychain item), readable by any process running as you;
- that process can derive the grant key and forge a reveal, a key backup or an approval;
- so **the secret boundary does not hold**. The rules still run — no plaintext route, approvals, `coffer run` masking — and still catch accidents, but they do not stop a determined same-user agent.
- so **approvals are off by default**. `secrets.require_approval` defaults by the build, by the same fact that decides where the master key lives: on in a signed release, off in a development build, where an approval a same-user process can forge would only add friction. A setting a person stores wins in both; turning it on needs nobody, and turning it off once it is on waits for the desktop app. Settings and the Secrets page say so in one line, and the Overview's "Secret approval is off" item is raised only where a signed build's default was turned off, so a development build is not nagged about its default.

A development build says so. The daemon reports itself as one, and the desktop app titles every presence prompt "Development build". Where a development machine has no LocalAuthentication, the app falls back to a confirmation dialog in its own window — never to no check.

The boundary holds only in a release signed with Coffer's Developer ID, under the hardened runtime and notarised, with the master key in a Keychain access group only those binaries can read.

## Loopback binding

The daemon binds `127.0.0.1` and nothing else. Uvicorn is handed the pre-bound socket rather than a host and port, so nothing downstream can widen the bind. Coffer listens on one other socket: the [local model proxy](/architecture/model-proxy), the daemon's sibling process, binds `127.0.0.1:38471` (`proxy_port` in `daemon-config.json`) and nothing else, and runs Host and Origin checks of its own (see [below](#the-model-proxy-listener)). Nothing else listens: Telegram is long-polled from inside the daemon, and each SeaTalk channel holds one outbound websocket connection. No channel needs a public URL, a tunnel or an inbound port.

## The Host and Origin checks

Binding to loopback stops remote hosts. It does not stop a browser, because any page you have open can send requests to `127.0.0.1`. Coffer runs two checks on every request before any route sees it. They cover the REST API, the `/mcp` endpoint, the `/api/v1/events` stream, websockets, the status probe and the served web UI. The daemon has one listener and every surface is on it, so there is no path to the daemon that skips the checks. This follows the MCP specification, which says an HTTP server must validate `Origin` on every connection. The same gap caused CVE-2025-49596 in the MCP Inspector, CVE-2024-28224 in Ollama and TS-2022-004/005 in Tailscale.

### Host: DNS rebinding

Suppose an attacker controls `evil.example` and re-points its DNS name at `127.0.0.1`. To the browser, the page is still same-origin with `evil.example`, so CORS never applies and the page can read the response body. The daemon puts its API token into the web UI's `index.html` (see below), so one request for `/` from that page would take the token, and with it everything the API can do: change Coffer's configuration, register a server, run up your provider bill.

DNS rebinding does not change the `Host` header. A rebound request still says `Host: evil.example:38470`. So the daemon accepts a request only when `Host` names `127.0.0.1`, `localhost` or `[::1]` **and** the port the request arrived on. It refuses anything else, including a request with no `Host` and a loopback name on another port:

```text
HTTP/1.1 403 Forbidden
{"error": {"code": "HOST_NOT_ALLOWED", "message": "Coffer only answers requests addressed to 127.0.0.1:38470 or localhost:38470; this one named evil.example:38470.", "details": null}}
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

`COFFER_ALLOWED_HOSTS` (comma-separated hostnames, or `*`) adds names that the Host check accepts. It never relaxes the Origin check. The backend test suite sets it because it drives the app in-process with made-up hostnames. A real installation does not need it, and a tagged release does not read it (nor `COFFER_CORS_ORIGINS` or `COFFER_DEV_CORS`), because the CLI starts the daemon from the caller's own environment.

### The model proxy listener

The [local model proxy](/architecture/model-proxy) is Coffer's second listener, and it runs its own checks before anything else. They are stricter than the daemon's. A request whose `Host` is not a loopback name on the port it arrived on gets 403, and `COFFER_ALLOWED_HOSTS` does not apply here. **Any** request that carries an `Origin` header gets 403 as well, because no browser page is a client of the proxy. Only then does a model route check the agent's local proxy token. The daemon's control routes are behind a separate control token from `~/.coffer/proxy.json`.

## The API token

### Minting and storage

At every start the daemon mints a fresh random URL-safe token from 32 bytes (256 bits) and writes it into `~/.coffer/daemon.json` along with the pid and port. The file is staged as a private temporary file and moved into place atomically, so it never exists with a mode wider than `0600`. The token is not persisted across restarts, not placed in any environment variable, and not written into any agent's config: the shim reads it from `daemon.json` at runtime.

### Checking it

Every route under `/api/v1/*` and the `/mcp` endpoint require an `X-Coffer-Token` header, compared in constant time against the daemon's in-process token. A missing or wrong token is `401`; a request that arrives before the daemon has published its token is `503`. The one unauthenticated API route is `GET /api/v1/daemon/status`, the readiness probe the CLI and shim call before they have a token; it returns lifecycle phase, version, executable, port, feature switches, machine name and an aggregate upstream health summary — nothing secret.

**Rotate…** on **Settings › Security** (or `POST /api/v1/daemon/rotate-token`) mints a new token, rewrites `daemon.json`, invalidates the old token immediately, and records `token_rotated` in the audit log.

### Getting it into the page

The web UI needs the token too, and a URL is the wrong channel: it ends up in browser history, session restore, screenshots and pasted bug reports. So the daemon hands it over in the **response body**. Whenever it serves `index.html` — for `/` and for every client-side route through the SPA fallback — it injects the token as a page global, in the first script in `<head>`, read from the same in-process value the token check compares against, so what the page holds cannot drift from what the API accepts.

- The document is served `Cache-Control: no-store`, with no ETag or Last-Modified, so a restarted daemon's browser never gets the previous daemon's token from a cache. Hashed files under `/assets` keep normal caching.
- The page persists nothing: reload after a daemon restart and it is authenticated against the new daemon.
- The address you open, `http://127.0.0.1:38470/` by default, carries no credential. The token arrives only in the page body.

The token in the page is exactly what makes the [Host check](#host-dns-rebinding) mandatory; neither exists without the other.

The desktop shell loads the same frontend as a local asset that nobody served, so there is no `index.html` to inject into. It supplies the same two globals over a Tauri IPC command before first render instead. The Vite dev server does the same from `daemon.json` during development. Each host is a credential *supplier*; the page reads one pair of globals either way.

### CORS

CORS grants exactly the cross-origin entries of the [Origin table](#origin-requests-from-other-sites): the desktop app's origins by default, and the development origins when you opt in. The browser-served UI is same-origin with the API and needs no CORS. CORS never uses a wildcard, and never allows credentials, so no cookie is ever attached. CORS and the Origin check read the same list, so they cannot disagree.

## The secret store

### Envelope encryption

Secrets live only as **Fernet ciphertext**, one file per secret, keyed by a **ref** — a name such as `github-token`. A ref's ciphertext is `~/.coffer/vault/secret/<ref>.enc`: the Fernet token and a newline, mode `0600` in `0700` directories. Refs that belong to this machine alone, such as the model proxy's tokens, live in `~/.coffer/local/secret/` and never enter the vault. Ciphertext is safe inside the vault repository because the key is not; `vault/secret/` is listed in the repository's `.git/info/exclude`, so it is not even committed until a sync remote carries secrets. Everything else in Coffer holds refs:

- An MCP server's config maps environment variables or headers to refs in `transport.secret_refs`. Its schema rejects a static `env` or header value that looks like a secret (`Bearer …`, `ghp_…`, `github_pat_…`, `sk-…`, `xox?-…`, a JWT prefix) and tells you to move it into `secret_refs`.
- A channel's bot token or app secret, a provider's API key, and the sync remote's push secret are refs.
- A **standalone secret** — one that belongs to no resource, such as a database password a skill needs — is a ref under `secret/<name>`, cited from files as `coffer://secret/<name>` and handed to a command by `coffer run` ([Secrets](/guides/secrets)).
- When you switch an agent onto a provider, the agent is pointed at the [local model proxy](/architecture/model-proxy) on loopback and authenticates with its own local proxy token (`coffer proxy token --agent-uid <uid>`, run by Claude Code's `apiKeyHelper` and Codex's provider `auth` command). The provider's key is never written into an agent's file or environment, and no route or command returns it: the daemon decrypts it and hands it to the proxy, which injects it upstream and holds it in memory only.

Plaintext exists in memory only between decrypt and the spawn or header injection that consumes it, and only after the [secret boundary](#a-secret-goes-somewhere-new-only-with-your-approval) has approved that destination. Registration probes every cited ref before writing the resource, so a missing secret fails with `SECRET_MISSING` and leaves nothing behind; deleting a secret that a resource still cites, or a standalone secret a skill cites, is refused with `409`; and deleting a resource releases any secret no remaining resource cites.

**The daemon is the sole secret-store owner.** Every surface — web UI, CLI, shim, desktop app — reaches secrets through the daemon's `/api/v1/secrets` routes; the CLI never touches the store in-process (an import contract forbids the CLI from importing the secret module or reaching the keychain), so each machine has exactly one reader of the key. Those routes store, list and delete; the only ones that release a value are the desktop app's presence-gated reveal and `coffer run`'s resolve of standalone secrets.

### The master key

The one secret that is not ciphertext is the Fernet master key, managed by one master-key component behind a storage port. Which store it uses is fixed by how the build was made, never by a setting or an environment variable:

| Build | Where the key lives | Defends against an offline copy of `~/.coffer/`? | Defends against a same-user process? |
| --- | --- | --- | --- |
| Signed release | One data-protection Keychain item (service `coffer`, account `master-key`) in an access group limited to Coffer's Team ID, with no presence flag | Yes | Yes — any other binary gets no access and no "Always Allow" dialog to click |
| Development, `file` (default) | `~/.coffer/master.key`, mode `0600` | No | No |
| Development, `keychain` (opt-in) | The login keychain, service `coffer`, entry `master-key` | Yes | No — any process can ask, and one "Always Allow" opens it for good |

**Presence gates the operations, not the key.** The Keychain item carries no Touch ID flag, so the signed daemon reads the key silently at every start — including a login-service restart after a crash with nobody at the keyboard — and keeps it in memory for its lifetime. What needs a person is letting plaintext out or sending a secret somewhere new.

**A signed release reads only its Keychain item.** It never looks in `master.key` or the login keychain, and refuses to move the key to a file.

**In a development build** you switch between the file and the keychain with **Settings → Security** or `coffer config set secrets.storage keychain`. Switching **moves the key, never re-encrypts the data**; the old copy is deleted last, and resolution is file-first, so an interrupted move always resolves to a working key.

Startup is fail-closed in every build. The daemon counts the ciphertext files *before* resolving the key, and creates a new key only when there are none. Ciphertext with no resolvable key stops the daemon with `MASTER_KEY_MISSING`; a keychain that refuses the read stops it with `SECRET_LOCKED` rather than creating a second key that would shadow it.

`keyring` is imported by exactly one module, the keyring adapter in the secret infrastructure package, and an import contract fails the build if surfaces or application code import it.

::: warning The signed-release Keychain backend is not yet proven on a real build
The access-group backend is built behind the storage port and tested against a fake Keychain. Whether a Developer-ID-signed `coffer-daemon` running as a bare binary outside an app bundle can claim the access group is still to be shown on a signed build; if it cannot, the daemon will run from inside the signed app bundle. Until the signed build exists, the development arrangement above is what runs.
:::

::: tip Back up the key
A copy of `~/.coffer` without its master key yields no secrets, and in a signed release the Keychain is the key's only home. Back it up in the desktop app, which writes a key file into a folder you pick behind a presence check. No command or browser page can export the key. See [Secrets → The master key and its backup](/guides/secrets#the-master-key-and-its-backup).
:::

## Outbound requests

The SSRF guard resolves a URL's host and refuses it if any resolved address is loopback, private (RFC 1918, `fc00::/7`), link-local, carrier-grade NAT (`100.64.0.0/10`), multicast, unspecified or reserved. A name that fails to resolve counts as blocked.

The rule ([Principles → Network defaults](/architecture/principles)) is that a URL Coffer probes or fetches on your behalf from something typed into a form passes the guard, while an endpoint you configure as your own does not. Four paths fetch from typed input. The first is the provider introspector, behind the three probes a connection editor runs before anything is saved — `POST /api/v1/models/list-models`, `/test-connection` and `/detect-protocol`. Each checks the base URL before its first request. A stored key never travels on its own: the `secret_ref` of a request is honoured only when a saved provider connection holds it for the same base URL, and only once that connection's key is an approved destination; any other pairing is refused before anything is decrypted. A key typed into the dialog travels as an inline value and touches no stored secret. Two cases skip the check:

- A base URL that really is loopback is not checked, so a local model runtime works. The exemption follows the URL itself, never the protocol the request names: labelling a metadata or LAN address `ollama` does not skip the guard.
- `detect-protocol` classifies a loopback host (`localhost`, `127.0.0.1`, `::1`, `0.0.0.0`, `host.docker.internal`) as `ollama` without sending any request.

The OpenAPI import of [custom tools](/guides/custom-tools) is the second: a spec URL typed into the import form is checked before it is fetched, and so is every redirect it answers with (the fetch is capped at 5 MiB and 20 seconds). A spec on a private host is imported as a file instead.

The third is the MCP servers page's test of a server that is not added yet (`POST /api/v1/resources/mcp_server/test-config`): an HTTP server's typed URL is checked before the test connects, and the MCP SDK follows a redirect only within that URL's own origin, so the test cannot be led to a host the guard did not see. A server on a private or loopback address is tested once it is added. The same test starts a stdio server only for the length of the test, in its own process group that is stopped whole when the test ends, and releases no stored secret to it — only values typed into the form for this test, which are redacted from the stderr lines and the message it returns.

The fourth is the Custom tools page's test of a request in a group that is not saved yet (`POST /api/v1/custom-tools/test`): the typed base URL is checked before the request is sent, the request follows no redirect, and no stored secret is sent, since the group has no approved binding yet. A group on a private host is tested once it is saved; after that its requests are the configured endpoint below.

So a probe of a non-Ollama endpoint on a private or link-local address is refused. Saving and using a connection are not probes, and the guard is not applied to the endpoints you configure as your own:

- **HTTP-transport MCP servers**, whose URL you registered — they commonly run on your own machine or network.
- **Saved custom-tool groups**, whose base URL you configured. Their requests follow no redirect, so the auth header only ever goes to that base URL.
- **Coffer's own model calls** and **transcription**, which go to the providers you configured.
- **Telegram and SeaTalk**, the IM platforms' own hosts, including the media URLs they hand back.
- **Vault sync**, which is a `git` subprocess against the remote you configured.
- **A skill's Git repository**, also a `git` subprocess against a URL you typed, run with no prompt, only the `https`, `http`, `ssh`, `git` and `file` transports and no submodules; a company's own Git host usually sits on a private address (see [Skills](/architecture/skills#git-repositories)).

One outbound request goes to an address Coffer chose itself rather than one you typed or configured, and so is not guarded: the **daily price-list refresh**. Once shortly after the daemon starts and then every 24 hours it sends a read-only `GET` to the file pydantic/genai-prices publishes, `https://raw.githubusercontent.com/pydantic/genai-prices/refs/heads/main/prices/new_data/v2/data.json`, with a 10-second timeout, a 16 MiB cap, no redirects, no credentials and nothing about you or your usage. The answer is validated before it is cached, and prices are never looked up while a request is being costed. **Refresh model prices** in Settings › General (`coffer config set prices.refresh off`) turns it off on a firewalled machine; Coffer then prices from the list shipped in the build.

The guard resolves DNS at validation time and the HTTP client resolves again when it connects, so a host that re-points between the two can slip past. Pinning the resolved address through to the client would break TLS certificate verification; for a single-user daemon where you typed the URL yourself, that residual risk is accepted.

## Commands Coffer runs for skill requirements

A skill can declare the command-line tools it needs ([Skill requirements](/architecture/skill-requirements)), and checking them runs two things on your machine: `<command> --version`, and the skill's login check. Both are held to the command the skill names — a bare name looked up on your `PATH`, and a login check whose first word must be that same command — and run as argv, never through a shell, with `stdin` closed and a timeout. A login check's output is discarded unread, so an account name or token it prints is never captured, logged or shown; only its exit status counts. Coffer runs no installer and no login command: installing is handed to your agent as a prompt ([the agent hand-off](/architecture/skill-requirements#the-agent-hand-off)), which asks it to check with you before anything that needs `sudo` and to leave logging in to you.

## Agent identity

When Coffer installs its MCP entry into an agent, it writes `coffer-mcp-shim --agent-uid <uid>`. The shim stamps that uid onto the MCP handshake, in the `_meta` field under the key `coffer/agent-uid`, and the gateway uses it for two things:

1. **Reach.** Every scoped resource is filtered by whether its scope covers the session's agent uid. A session with no identity — a shim you configured by hand — matches only unscoped resources, so it sees strictly less, never more. An older shim sending a name-based key is read as unidentified; there is no fallback that could match a stale label against a scope.
2. **Attribution.** Every builtin tool call carries an `agent` argument naming the caller. The gateway **always** sets it from the handshake identity (resolved to the agent's current name): a value the client supplied is dropped unconditionally, and with no identity the argument is simply absent. No builtin tool advertises the argument, so a model has nothing to fill in.

The identity is self-reported by a process running as you. It is not a security boundary against a malicious local process — any such process already holds the token — and the spec says so rather than implying stronger isolation.

## Channels and owner pairing

A channel is the one surface through which someone outside your machine can make an agent act, so it has exactly one gate: **owner pairing**.

- You issue a pairing code from the channel's page. A code is 8 characters from an alphabet without look-alikes (no `0`, `O`, `1`, `I`), single-use, valid for one hour, allows 10 wrong guesses before it is invalidated, and lives only in memory — a daemon restart drops it.
- You send the code to the bot from your own account (or tap the start link that carries it). That binds your platform identity as the channel's owner and records `channel_paired` in the audit log.
- From then on the channel obeys only messages whose sender is the owner. In a group, a message addressed to the bot by anyone else gets a one-line refusal; in a paired chat, a message from a different member is ignored silently and cannot re-pair the channel; an unpaired direct chat can do nothing but present a pairing code. When a sender's identity cannot be established in a group, the message is refused, never assumed to be the owner's.
- A channel's **inverted scope** limits which agents it may drive at all, and a channel whose scope is empty does not start.

Channel secrets are refs, resolved from the secret store when the adapter starts.

### Group privacy {#group-privacy}

A group is the one place where the agent's answer is read by people other than the owner. In a group turn the agent can still read the owner's memory, knowledge and files, exactly as in a direct chat, and a SeaTalk group reply cannot be recalled by the platform. Coffer does not filter reply content: there is no secret, personal-data or memory-overlap scanning. The owner's safeguard is deleting a reply with `/del` or the 🗑 button (Telegram deletes the message; SeaTalk rewrites the reply's cards into a neutral “Withdrawn” card). Each withdrawal is written to the audit log with the owner, the channel and the number of messages, never the content.

An agent that is tricked by a group member can still say something private. An owner who needs a stronger guarantee should not pair the bot with a group that contains people they do not trust. See [Channels](/guides/channels#group-privacy).

## What goes into logs and audit

- **Logs** (`~/.coffer/logs/`, one JSON object per line) record events, identifiers and errors. No code path logs a secret value, a token or a decrypted secret.
- **Audit** records every lifecycle change with its actor. Secret events (`secret_set`, `secret_revealed`, `secret_deleted`, `secret_resolved`, `secret_imported` and the `secret_approval_*` events) record the **ref**, the secret's name or the destination only. Resource configs pass through the kind's audit redactor first — the MCP kind strips `transport.env` and `transport.headers` entirely — so a value pasted into the wrong field still does not reach the audit log. Master-key events (`master_key_relocated`, `master_key_exported`, `master_key_imported`) record that the event happened, not the key.
- **The sync history** stores the remote's commit and errors after the push secret has been redacted out.

## Sync carries ciphertext only

Vault sync pulls and pushes the vault repository with a git remote you own. It is off until you configure a remote, and its security rests on what does and does not travel:

- **Secrets travel only if you opt in** (**Include encrypted secrets**), and then only as Fernet ciphertext, the `secret/<ref>.enc` files. Until then `secret/` is excluded from the repository. What lands in the repository cannot be decrypted on its own, and ciphertext that has been pushed cannot be withdrawn: revoking a secret means rotating it. Machine-local ciphertext in `local/secret/` never travels.
- **The master key never travels with the data.** You carry it between machines yourself: the desktop app writes a passphrase-protected key backup on one machine behind a presence check, **Settings › Security › Import a master key** installs it on another, and shows both fingerprints so you can compare the two. Importing a different key first keeps the existing one as a backup — a timestamped `master.key.bak-*` file in a development build, a second Keychain item in a signed release — because it may be the only key that decrypts existing ciphertext.
- **The push token goes only to the URL it was approved for.** Pointing it at a new remote URL waits for an approval, like any new destination.
- **A machine without the matching key** reports the refs it holds ciphertext for but cannot decrypt, and the **Machines** tab flags a machine whose key fingerprint differs, rather than failing silently.
- **The secret boundary stays on the machine.** Its bindings, approvals and switches are in `local/secret-boundary/`, never in the vault, so another machine cannot pre-approve a destination for this one.
- **Reach does not travel.** Which resources are enabled, and for which agents, is decided on each machine, so another machine's round can never widen what this one exposes.
- **Deletions are guarded.** A round that would lose 20 files or more than 20% of an area, in either direction, holds for your answer.
- **Conflicting ciphertexts are never shown to you.** Two ciphertexts for one ref are ordered by the encryption time the token carries in clear, and the fresher wins; and a secret has no readable history or restore through the vault's History.

See [Vault sync](/architecture/vault-sync) for the full protocol.

## Trade-offs and alternatives

- **Token scopes as the boundary** — an admin token for changes, per-agent tokens for the gateway. Rejected: the `coffer` CLI runs as you, so an agent that can run it holds the admin token, and registering an MCP server is running a command, which the agent can do with its own shell anyway. It guards "who may change config" and leaves "where may a secret go" open. Per-agent tokens remain useful for attribution, not as the boundary.
- **Read-deny rules on `~/.coffer` in every agent's config.** Rejected: agents are meant to read knowledge and memory there, and once no plaintext and no key lives there, the rule protects nothing. It does nothing in bypass mode.
- **Plaintext on the CLI with a Touch ID reuse window** (the password-manager CLI model). Rejected: a window is a gift to whoever acts next — an agent started from that terminal inherits the session — and the value lands in a terminal the agent may be reading.
- **A presence flag on the master key itself.** Rejected: the daemon would prompt at every start and run locked after an unattended crash restart. Presence belongs on the operations that let plaintext out.
- **The daemon as a separate OS user.** Rejected: an installer with privilege separation for a single-user tool, while upstream servers still run as you, which puts their environments back in reach.
- **Every secret as its own Keychain item.** Rejected: vault sync could no longer carry ciphertext between your machines, and one key in an access group already makes a copied store useless.
- **A file-default master key with a keychain opt-in** (the development arrangement). Kept only for development builds: under an unsigned, frequently rebuilt binary macOS re-prompts on every rebuild, and only a Team ID signature removes that.
- **A passphrase-derived key.** Rejected for the default: a prompt at every daemon start, and a forgotten passphrase loses every secret.
- **Persisting the API token across restarts.** Rejected: a long-lived on-disk token that unlocks the secret endpoints is worse than a per-process one.
- **Putting the token in the URL.** Rejected: URLs leak into history, screenshots and bug reports; a response body does not.
- **Relying on loopback binding alone.** Rejected: that is exactly the gap DNS rebinding walks through.
- **Per-tool approval prompts for agents.** Not built: every instruction already comes from the paired owner, so a per-tool prompt would only re-confirm what the owner asked for. Approvals are asked for only where a secret would go somewhere new.

## Where it lives in the code

| Package | Contents |
| --- | --- |
| The HTTP surface | The token check, the `Host` and `Origin` checks, the CORS allowlist and middleware order, serving the UI with the injected token, and the secret-boundary routes (presence-gated reveal and key backup, approvals, the `coffer run` resolve, scan and import). |
| The daemon infrastructure | Token minting, `daemon.json`, `0600` writes, the loopback bind. |
| The secret infrastructure | Encrypted store, master key and its storage backends, keyring adapter, binding and approval store, plaintext scan. |
| The secret application layer | The secret boundary (destinations, bindings, approvals), presence grants, the guarded resolver. |
| The CLI surface | `coffer run` and its output masking. |
| `desktop/` | The desktop app's presence check, grant signing and approval notifications. |
| The network infrastructure | SSRF guard. |
| The MCP gateway and the channel application layer | Handshake identity and the `agent` argument overwrite; pairing codes and the owner gate. |

## Related

- [Secrets guide](/guides/secrets)
- [Secret store guide](/guides/secret-store)
- [Security policy](/contributing/security) — how to report a vulnerability.
- [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)
- [The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/master-key-lives-in-the-macos-keychain.md)
- [Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/standalone-secrets-are-named-references-injected-into-one-child.md)
- [The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/master-key-lives-in-the-macos-keychain.md)
- [A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-auth-and-origin-guard.md)
- [Per-Agent Resource Scope](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/per-agent-resource-scope.md)
- [Managed Agents Run With Full Permissions; Owner Pairing Is the Gate](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/managed-agents-run-with-full-permissions.md)
- Specs: [secret](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/secret/spec.md), [desktop-app](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/desktop-app/spec.md), [daemon](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/daemon/spec.md), [channels](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/channels/spec.md)
