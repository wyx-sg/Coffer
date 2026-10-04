# API-Key Providers Are Reached Through a Separate Local Model Proxy That Relays Bytes Unchanged

**Status**: Accepted
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md), [Usage Is Metered at the Proxy; Subscription Agents Are Not Metered](usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota.md), [The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](master-key-lives-in-the-macos-keychain.md), [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md), [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), [The Daemon Binds a Fixed Port and Refuses to Start Without It](daemon-binds-a-fixed-port.md), [The Daemon Is Resident: It Never Idles Out, and a Login Service Restarts Only a Crash](daemon-is-a-resident-login-service.md), [A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](daemon-auth-and-origin-guard.md), [Audit Every Change With Its Actor, Log Invocations Without Payloads, Prune Per Table](audit-and-retention.md), [Distribution — Three PyInstaller Binaries, Shipped as a CLI Archive and a Desktop App](distribution-pyinstaller.md), [Agent Mechanisms Are Optional Facets on the Descriptor, and Projection Is One Registry](agent-mechanisms-are-optional-facets-on-the-descriptor.md), [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters](one-level-triggered-reconciler-compares-parameters.md), [principles](../../docs-site/architecture/principles.md) (Secrets; Network defaults), research note [provider switching](../research/provider-switching.md), spec provider-switching "Reach API-key and local connections through the local model proxy", spec provider-switching "Project into Claude Code settings without clobbering them", spec provider-switching "Project into Codex config without overwriting it", spec provider-switching "Authenticate each agent to the proxy with its own local token", spec secret "Hold plaintext only in memory at the moment of use", PR #412, PR #464

## Context

An agent on an API-key connection has to call a model with a key that Coffer
holds as ciphertext, and the agent is a process Coffer neither owns nor trusts
with a provider key: Claude Code and Codex run as the user, a managed agent runs
with full permissions, and a prompt-injected agent can run any command the user
can. Two questions follow, and they were answered in two steps.

The first step was to **project** the connection into the agent's own config
file ([LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md))
and to keep the real key out of that file. The projection wrote the upstream
endpoint plus a key indirection: for Claude Code an `apiKeyHelper` that asked the
daemon for the real key (`coffer provider key --connection-uid <uid>`, answering
404 and exiting 4 for a connection that no longer reached an agent, so a stale
helper failed closed); for Codex `env_key = "COFFER_PROVIDER_KEY"`, with the real
key merged into the environment of every Codex process Coffer spawned and
`COFFER_PROVIDER_KEY` added to Codex's `shell_environment_policy.exclude` so `env`
in a turn would not print it. That design rested on a rule that survives this ADR
unchanged: **no raw provider key is ever written into an agent's native config
file.** Those files are plaintext under the home directory, copied into dotfile
repos and backups, read by other tools and restored wholesale by the user, and
the principles say secret plaintext exists only in memory between decrypt and the
injection that consumes it.

The second step is this ADR, because two things the product needs cannot be
done from a config file:

- **Usage and cost of API-key traffic.** Nothing Coffer runs sees the
  requests, so usage could only be estimated from transcripts, which do not
  record every request an agent makes (background, compaction and classifier
  calls) and whose format is the agent's internal business.
- **The raw key out of the agent's reach.** Codex held the real key in its
  environment. PR #464 had to exclude `COFFER_PROVIDER_KEY` from Codex's
  shell commands after it was found reachable by `env`, and a Codex started
  from the user's own terminal had no key at all unless the user exported it;
  Claude Code's helper printed the real key to anyone who could run it.

A proxy was rejected at first for three reasons: a resident component on every
model call, the daemon going down taking every agent with it, and the proxy
seeing every prompt. The first is measured cheap — gateway overhead is
microseconds to low milliseconds per request even in Python (vendor-published
benchmarks put LiteLLM at about 600 µs at 5k RPS), against a time-to-first-token
of seconds at single-user rates. The second and third are design questions
this ADR answers: which process the proxy is, and what it may record.

The agents fix the contract a proxy has to meet. From Claude Code's gateway
documentation (code.claude.com/docs/en/llm-gateway-protocol): forward
`anthropic-version` and `anthropic-beta` unchanged and treat every
`anthropic-*` header and body field as an open list; never buffer a stream and
forward pings, because Claude Code aborts a stream silent for 300 s by
counting relayed bytes; pass `retry-after`, `x-should-retry` and
`anthropic-ratelimit-*` through; forward error bodies unmodified, because
Claude Code's recovery matches the upstream's wording; never touch `system`,
`tools` or earlier messages, or prompt caching and thinking signatures break.
`apiKeyHelper` output is sent as both `x-api-key` and `Authorization`, cached
five minutes. Setting `ANTHROPIC_BASE_URL` alone leaves a claude.ai login
active and sends subscription traffic through the gateway. From Codex's
config reference: a custom `[model_providers.<id>]` accepts `base_url`,
`wire_api` (only `"responses"`; `"chat"` was deprecated in December 2025,
openai/codex discussion #7782, and configs carrying it no longer load),
`supports_websockets`, `requires_openai_auth` and a command-backed `auth`
table (`command`, `args`, `timeout_ms`, `refresh_interval_ms`); pointing the
built-in `openai` provider at another base URL makes Codex try the Responses
WebSocket transport first and stall (codex-tools #202).

Subscription logins are a separate matter. Anthropic's legal and compliance
page (code.claude.com/docs/en/legal-and-compliance, clarified 2026-02-19) says
developers "may not collect, store, or intermediate Claude.ai credentials or
session tokens", and LiteLLM's issue tracker shows what goes wrong when a proxy
carries them anyway: an OAuth token forwarded to a third-party `api_base`
(#42172) and a stripped billing header turning into 429s (#29572).

## Options Considered

### Option A — Project the upstream endpoint and a key indirection into each agent's config (the design this replaced)

The agent's file names the upstream `base_url`, and the real key reaches the
agent at use time through a Coffer-resolved indirection: Claude Code's
`apiKeyHelper` (stdout is the key, re-invoked periodically) or Codex's
`env_key` environment variable. The key stays Fernet ciphertext in the store
under an opaque ref.

- **Pros.** No component on the request path; an agent keeps working while
  Coffer is stopped, as long as it can still get its key; nothing new to
  supervise; no plaintext key in any file Coffer writes; a key rotation in Coffer
  reaches Claude Code on its next helper call; removing the connection makes the
  helper fail closed.
- **Cons.** It meters nothing, so it cannot deliver
  what the Usage page needs. The real key still reaches
  the agent: it sits in every Coffer-spawned Codex process's environment,
  guarded only by a shell-policy exclude the user or a later Codex default can
  undo, and Claude Code's helper prints it to any caller. A terminal Codex needs
  a manual export of the real key. Rotating a Codex key reaches only processes
  started after it. Switching connection means a file rewrite and an agent
  restart. Claude Code depends on the daemon being reachable when it fetches a
  key, and uninstalling Coffer leaves a helper line that fails.
- **Why it loses.** It cannot meet the requirement, and the one secret it
  still hands to an agent is a real provider key.

### Option A2 — Write the key into the native file (the cc-switch shape)

Put the raw key in `env.ANTHROPIC_AUTH_TOKEN` and the Codex provider table.

- **Pros.** Works with no daemon, no helper and no shell export; the simplest
  thing that runs.
- **Cons.** The key lands in plaintext in files that are backed up, synced by
  dotfile tools and committed to git by accident; a rotation means rewriting
  every file on every machine; it breaks the rule every other Coffer secret
  follows.
- **Why it loses.** The secrets principle admits no exception, and the proxy
  makes the exception unnecessary.

### Option A3 — Store the key in the OS keychain and point the agents at it

Write the key to the macOS keychain and let each agent read it through a helper
such as `security find-generic-password`.

- **Pros.** An OS-grade secret store; no daemon dependency for the read.
- **Cons.** Codex has no keychain hook, only `env_key`, so it still needs
  launch-time injection; a keychain entry is a second copy of a secret Coffer
  already stores and must be kept in step on rotation and sync; and any binary
  allowed to run the helper reads the key, the agent's included
  ([The Master Key Lives in a Keychain Access Group](master-key-lives-in-the-macos-keychain.md)
  records how weak per-application keychain trust is against a same-user
  process).
- **Why it loses.** It duplicates the store and does not work for Codex.

### Option B — A proxy inside the daemon

Mount the proxy routes on the daemon's own server.

- **Pros.** One process; the proxy reads the credential store and writes
  usage without any inter-process hop; nothing new to supervise or package.
- **Cons.** The daemon restarts for every upgrade and runs migrations at
  start (a start measured at 4.8–13.9 s, the reason PR #412 widened the
  handshake), and each restart would cut every in-flight model stream of
  every agent, including the ones in the user's own terminal. The daemon's
  event loop also runs the MCP gateway, channels, sync and the chat drivers;
  a blocking bug in any of them stalls every model call. This is the exact
  failure — "daemon down means both agents dead" — that made a proxy look too
  risky in the first place.
- **Why it loses.** It puts the hottest path in the process that restarts
  most and does the most.

### Option C — A separate, supervised proxy process from the same binary (chosen)

The proxy is its own small process, started from the daemon's frozen binary in
a proxy mode (`coffer-daemon proxy`), so there is no fourth binary to build, sign and ship. The daemon
supervises it — spawns it at start if it is not already running, health-checks
it, restarts it on a crash — and a daemon restart or upgrade does not stop it:
the new daemon finds the running proxy through `~/.coffer/proxy.json`
(`port`, `pid`, `started_at`, `version` and a control token, mode `0600`) and re-attaches.
A proxy from an older build drains its open streams and is replaced once idle.

**Surface.** It binds `127.0.0.1` only, with no option for another interface,
on a fixed port (`proxy_port` in `daemon-config.json`, 38471 by default), so the value written into the
agents' files never changes on its own
([The Daemon Binds a Fixed Port and Refuses to Start Without It](daemon-binds-a-fixed-port.md)).
It serves only `POST /anthropic/v1/messages`,
`POST /anthropic/v1/messages/count_tokens`, `GET /anthropic/v1/models`,
`POST /openai/v1/responses` and `HEAD /api/hello`, plus its own control
route; everything else is 404. A request with any `Origin` header or a `Host`
other than the loopback address and port is refused, as the daemon refuses
them ([A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](daemon-auth-and-origin-guard.md)).

**Local token per agent.** Each managed agent has its own random 256-bit
token, compared in constant time, accepted as `Authorization: Bearer` or
`x-api-key`. It is kept as Fernet ciphertext in the secret store under the
machine-local ref `proxy-token/<agent_uid>`, which vault sync skips, and the proxy
receives only its SHA-256 digest. It unlocks the loopback proxy and nothing else,
and it tells the proxy which agent is calling, which is how usage is attributed. A request
carrying any other credential — a claude.ai OAuth bearer such as
`sk-ant-oat…`, a real provider key — is refused with 401 and nothing is
forwarded. Client credentials are always stripped; the proxy injects the real
key for the upstream it chose. The threat model is stated plainly: the token
keeps browsers and other users' processes out, not a same-user process that
can read what the agent can read; the secret boundary is the key, which the
agent never holds
([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)).

**Pointing the agents.**

- Claude Code, when it runs on an API-key connection:
  `env.ANTHROPIC_BASE_URL = http://127.0.0.1:<port>/anthropic`; `NO_PROXY`
  gains `127.0.0.1,localhost` so a corporate `HTTPS_PROXY` never captures the
  loopback leg; `apiKeyHelper = <coffer> proxy token --agent-uid <uid>`, which
  prints the agent's local token; the model keys from the agent's binding, plus
  `ANTHROPIC_DEFAULT_HAIKU_MODEL`, because behind a custom base URL Claude Code
  otherwise runs background tasks on the main model, a silent cost multiplier
  its protocol page names.
- Codex: `model_provider = "coffer"` and a `[model_providers.coffer]` table
  with `base_url = http://127.0.0.1:<port>/openai/v1`,
  `wire_api = "responses"`, `supports_websockets = false`,
  `requires_openai_auth = false` and
  `auth = {command = "<coffer>", args = ["proxy", "token", "--agent-uid", "<uid>"]}`.
  A terminal Codex then works with no export, because it runs the command
  itself. The command-backed `auth` table (`ModelProviderAuthInfo`) needs Codex
  0.155.1 or later, the version it was confirmed on; no process's environment
  carries a proxy token either.
- Both helper lines name the CLI by absolute path, because an agent started
  from the Dock gets no login `PATH`.
- `model_catalog_json`, scope-driven reach, the agent's own connection pointer,
  the boot check and `use-builtin` are described by
  [LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md).
  Switching between two API-key connections changes the proxy's route, not the
  agent's file; a switch between a subscription login and an API-key connection
  is still a file write.

**Keys.** The daemon remains the only holder of the master key. It decrypts
the keys of the connections the proxy serves and hands them to the proxy over
its authenticated loopback control route, on spawn, on re-attach and whenever
a connection changes; the proxy holds them only in memory and injects them as
headers. They are never written to disk, argv, the environment or a log.

**Relay.** Same wire in, same wire out: the Anthropic route forwards only to an
Anthropic-Messages upstream and the Responses route only to a Responses
upstream. The request body is forwarded byte for byte; the proxy parses a copy
only to read `model` and `stream`. Every header is forwarded except hop-by-hop
headers, `host`, the client's credentials and `accept-encoding` (the proxy
asks the upstream for an uncompressed stream so its reader sees plain SSE, and
never compresses toward the agent). Status, headers and body chunks go back
as received, pings and comments included, error bodies verbatim. A usage
reader consumes a copy of the bytes beside the relay; a reader failure never
touches the relay. Timeouts: 10 s to connect, no total timeout, at least
300 s of upstream read idleness, matching both agents' own watchdogs. The
upstream leg honours the user's `HTTPS_PROXY` for a remote member; a local
runtime is reached directly.

**Routing.** An agent's requests go to exactly one connection: the one the
agent is switched onto. The proxy never moves a request to another connection
and never substitutes a model. Whatever the upstream answers, an error status
included, reaches the agent as sent (`retry-after`, `x-should-retry` and the
rate-limit headers with it), so the agent's own retry logic acts on its
vendor's words; both agents already retry (Codex four request and five stream
retries by default). When the upstream cannot be reached — a connect, TLS or
DNS error, or a first-byte timeout — the proxy answers 502 in the wire's own
error shape.

**Logging.** Metadata only: the usage record. No
bodies, no prompts, no completions, no credentials; `authorization`,
`x-api-key` and cookies are redacted at the logger, as the audit ADR already
requires of invocation logs.

**Local runtimes.** Ollama, LM Studio, vLLM and llama-server are upstreams of
the same routes, keyless or with an optional key, detected read-only with a
minimum version per wire. "No protocol translation" stands: every mainstream
runtime serves both wires itself.

**Subscription traffic never goes through it.** An agent on its own login has
no proxy base URL and no helper projected, and the proxy refuses the
credential such an agent would send.

- **Pros.** Metering becomes possible for every API-key request,
  whoever started the agent. The only secret an agent holds is a local token
  that unlocks a loopback relay; the real key never enters an agent's config
  or environment, and the Codex terminal case needs no export. A daemon
  restart or upgrade cuts no stream. Switching between two API-key
  connections changes the proxy's route, not the agent's file.
- **Cons.** A resident process on every API-key model call: if the proxy is
  down, those calls fail until the daemon restarts it. The proxy holds
  decrypted provider keys in memory for its lifetime, which the principles'
  Secrets clause names. It sees every prompt in transit, which the
  metadata-only rule keeps out of anything stored. And it is one more process
  to supervise, version and drain on upgrade.
- **Why it wins.** It is the only option that meters without
  putting the hot path inside the process that restarts on every upgrade.

### Option D — Adopt an existing gateway (LiteLLM proxy or claude-code-router) as a dependency

Ship LiteLLM's proxy or claude-code-router beside Coffer and generate its
config from Coffer's connections.

- **Pros.** Mature routing, fallbacks, cooldowns and spend tracking already
  exist; a large user base finds the bugs.
- **Cons.** The bugs found are in exactly the places this contract depends on.
  LiteLLM did not forward `anthropic-beta` values to a cloud upstream
  (#15299), under-billed cache writes by pricing the `message_start` breakdown
  and ignoring the larger final total (#42663), forwarded a client's OAuth
  token to a third-party `api_base` (#42172) and stripped a billing header
  (#29572); its spend tracking wants Postgres. claude-code-router is built
  around protocol translation, whose transformers have mangled tool-call
  argument deltas (#1397) and dropped Gemini thought signatures (#1032); its
  scenario routing sends background, thinking and long-context requests to
  different models, which is what produces "Invalid signature in thinking
  block"; it is a Node.js runtime, outside the principles' two languages; and
  it logs at `debug` by default. Either way Coffer would still write both
  agents' configs, run its own usage reader for the Usage page and supervise
  a foreign process whose upgrades it does not control.
- **Why it loses.** Coffer needs a narrow, pass-through relay with strict
  forwarding and logging rules; both tools are broad translators whose
  breadth is the source of the failures above, and each adds a runtime or a
  database to the distribution.

### Option E — Route subscription traffic through the proxy too

Point every agent at the proxy, logged in or not, so all traffic is metered in
one place.

- **Pros.** One mechanism and one Usage source for every agent.
- **Cons.** The proxy would carry claude.ai OAuth tokens, which Anthropic's
  credential policy says third-party developers may not intermediate; the
  proxy would have to forward the OAuth capability in `anthropic-beta` and the
  billing headers exactly, or requests fail (LiteLLM #29572); Remote Control
  is disabled for any non-Anthropic base URL; and the number a subscription
  user cares about is the server's remaining allowance, which request metering
  does not give
  ([Usage Is Metered at the Proxy; Subscription Agents Are Not Metered](usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota.md)).
- **Why it loses.** It takes on a policy risk and a breakage surface for a
  number that official feeds already provide.

### Option F — Fail a request over to another connection that serves the same model

Within Option C, let the proxy hold a pool per agent: its own connection first,
then the other enabled connections that reach the same agent type, speak the
same protocol, are switched on as a fallback and list the requested model, in
the order of the Model providers list. A request that failed before its first
content byte (a connect error, a 5xx, 529, 429, a rejected key, a first-byte
timeout, an early `event: error`) would move to the next member, with cool-downs
from `retry-after`, a held response bounded to 64 KiB and 5 seconds, session
affinity to keep the prompt cache warm, and a `provider_failover` audit row per
move. This was built and shipped, then removed.

- **Pros.** A transient outage at one gateway could be hidden from the agent
  when a second connection served the identical model id.
- **Cons.** It only ever applies when two connections list the *same* model id,
  and real use showed none: zero proxied requests were failed over. It was
  nevertheless the most complex part of the proxy — a pool and its ordering, a
  response hold before the first content byte, member health and cool-downs,
  disabling a member on 401 or 403, a per-attempt usage record with a
  `failed_over` flag, an audit event and a drag-to-reorder list that existed
  only to set priority. Each of those is a place a request can be delayed,
  duplicated or sent somewhere the user did not expect, and a local runtime had
  to be special-cased so a prompt meant for a local model never left the machine.
  Both agents already retry transient errors themselves.
- **Why it loses.** A mechanism that serves a case that did not occur, at the
  cost of the proxy's simplest property — a request goes where the user pointed
  the agent and what comes back is what that upstream said — is not worth keeping.

## Decision

An API-key connection reaches Claude Code and Codex through a local model
proxy: a separate process started from the daemon's binary, supervised by the
daemon and surviving its restarts, bound to `127.0.0.1` on a fixed port. Each
agent is pointed at it through its own config — `ANTHROPIC_BASE_URL` plus an
`apiKeyHelper` for Claude Code, a custom `coffer` provider with
`wire_api = "responses"`, WebSockets off and command-based auth for Codex —
and authenticates with a per-agent local token that also attributes its usage.
The proxy relays each request byte for byte to an upstream of the same wire,
reads usage from a copy of the stream, routes each agent to exactly one
connection, returns the upstream's own errors as sent (502 when the upstream
cannot be reached), and logs metadata only.
Agents on a subscription login are never pointed at it, and it refuses their
credentials.

The Claude Code writer projects the proxy's URL, the proxy-token helper,
`NO_PROXY` and the pinned background model; the Codex writer projects the
proxy's URL, `supports_websockets = false`, `requires_openai_auth = false` and
the `auth` command. No command and no route returns a provider key to an agent:
the `coffer provider key` helper and the key route it called are gone, and no
process's environment carries a provider key. The rule that no raw provider key
is ever written into a native config file holds for the agents' environments
too.

Rules a future change must respect:

- No protocol translation in 1.0: a route forwards only to an upstream of its
  own wire. Adding translation is a new decision.
- The proxy never forwards a client credential and never accepts one that is
  not a Coffer proxy token.
- A request goes to the agent's own connection only; the proxy never moves it
  to another connection and never changes the model.
- `anthropic-*` headers and body fields are an open list; nothing is
  allow-listed, reordered or re-serialized.
- Nothing the proxy stores or logs contains a body, a prompt, a completion or
  a credential.
- A projection for a subscription-mode agent never writes the proxy URL or
  helper.

## Consequences

- **Principles.** The Secrets clause names the proxy: it holds decrypted
  provider keys in memory for its lifetime, as a header-injection consumer,
  receives them from the daemon over its authenticated loopback control route,
  and never holds the master key. The process model — one daemon — has the proxy
  as its only sibling process, supervised by the daemon.
- **Distribution.** No new binary: the proxy mode ships inside
  `coffer-daemon`, so the three-binary layout of
  [Distribution — Three PyInstaller Binaries](distribution-pyinstaller.md)
  holds, and the release smoke test boots the proxy mode too.
- **Projection.** The provider projection writers write the proxy form through
  the shared native-config writer and the projection registry; a file whose
  values went stale is re-projected by the reconciler.
- **Provider keys and approval.** The proxy holds a connection's key only once
  the key may go to the connection's base URL; a replaced key or a moved base URL
  waits for a person's approval, and the daemon pushes the proxy its state again
  when the approval is applied, with no restart.
- **Tests.** A byte-equality relay test over recorded SSE, pings included; an
  open-list header test (an unknown `anthropic-beta` value and an unknown body
  field arrive untouched); an upstream-error test (a 503 reaches the agent as sent, and an unreachable
  upstream answers 502); auth tests (no token, an OAuth-shaped token, a
  foreign `Host`, an `Origin` present).
- The architecture page [The local model proxy](../../docs-site/architecture/model-proxy.md)
  explains the proxy, the token and what it does not log.
- If the proxy is down, API-key model calls fail until the daemon restarts it;
  `coffer proxy status` shows what the supervisor sees.
