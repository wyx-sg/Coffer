# API-Key Providers Are Reached Through a Separate Local Model Proxy That Relays Bytes Unchanged

**Status**: Proposed
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md), [Provider Keys Never Land in an Agent's Native Config](provider-keys-never-land-in-native-config.md), [Usage Is Metered at the Proxy; Subscription Agents Show Only Their Official Remaining Quota](usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota.md), [Envelope-Encrypted Credential Store](envelope-encrypted-credential-store.md), [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), [The Daemon Binds a Fixed Port and Refuses to Start Without It](daemon-binds-a-fixed-port.md), [The Daemon Is Resident: It Never Idles Out, and a Login Service Restarts Only a Crash](daemon-is-a-resident-login-service.md), [A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](daemon-auth-and-origin-guard.md), [Audit Every Change With Its Actor, Log Invocations Without Payloads, Prune Per Table](audit-and-retention.md), [Distribution — Three PyInstaller Binaries, Shipped as a CLI Archive and a Desktop App](distribution-pyinstaller.md), [Agent Mechanisms Are Optional Facets on the Descriptor, and Projection Is One Registry](agent-mechanisms-are-optional-facets-on-the-descriptor.md), [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters](one-level-triggered-reconciler-compares-parameters.md), [principles](../../docs-site/architecture/principles.md) (Credentials; Network defaults; "Not a firewall or security boundary"), research note [provider switching](../research/provider-switching.md), spec provider-switching "Project into Claude Code settings without clobbering them", spec provider-switching "Project into Codex config without clobbering it", spec provider-switching "Resolve a key for exactly one connection", spec credentials "Hold plaintext only in memory at the moment of use", PR #412, PR #464

## Context

Today an API-key connection reaches an agent by being written into the agent's
own config file
([LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md)):
Claude Code gets the upstream `ANTHROPIC_BASE_URL` and an `apiKeyHelper` that
asks the daemon for the real key; Codex gets a `[model_providers.coffer]`
table with the upstream `base_url` and `env_key = "COFFER_PROVIDER_KEY"`, the
real key being merged into the environment of every Codex process Coffer
spawns ([Provider Keys Never Land in an Agent's Native Config](provider-keys-never-land-in-native-config.md)).

Three things the 1.0 plan requires cannot be done from a config file:

- **Usage and cost of API-key traffic.** Nothing Coffer runs sees the
  requests, so usage could only be estimated from transcripts, which do not
  record every request an agent makes (background, compaction and classifier
  calls) and whose format is the agent's internal business.
- **Failover.** A connection with several keys, or several endpoints serving
  the same model, has no way to move a failing request to a healthy member.
- **The raw key out of the agent's reach.** Codex holds the real key in its
  environment. PR #464 had to exclude `COFFER_PROVIDER_KEY` from Codex's
  shell commands after it was found reachable by `env`, and a Codex started
  from the user's own terminal has no key at all unless the user exports it.

The earlier ADRs rejected a proxy for three reasons: a resident component on
every model call, the daemon going down taking every agent with it, and the
proxy seeing every prompt. The first is measured cheap — gateway overhead is
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

### Option A — Keep projecting the upstream endpoint and a key indirection into each agent's config (today)

The design of the two ADRs above, unchanged.

- **Pros.** No component on the request path; an agent keeps working while
  Coffer is stopped, as long as it can still get its key; nothing new to
  supervise.
- **Cons.** It meters nothing and fails over nothing, so it cannot deliver
  the two things the 1.0 Usage page and failover need. The real key sits in
  every Coffer-spawned Codex process's environment, guarded only by a
  shell-policy exclude the user or a later Codex default can undo. A terminal
  Codex needs a manual export of the real key. Rotating a Codex key reaches
  only processes started after it. Switching connection means a file rewrite
  and an agent restart.
- **Why it loses.** It cannot meet the requirement, and the one secret it
  still hands to an agent is a real provider key.

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
  failure — "daemon down means both agents dead" — for which the earlier ADRs
  rejected a proxy.
- **Why it loses.** It puts the hottest path in the process that restarts
  most and does the most.

### Option C — A separate, supervised proxy process from the same binary (chosen)

The proxy is its own small process, started from the daemon's frozen binary in
a proxy mode, so there is no fourth binary to build, sign and ship. The daemon
supervises it — spawns it at start if it is not already running, health-checks
it, restarts it on a crash — and a daemon restart or upgrade does not stop it:
the new daemon finds the running proxy through `~/.coffer/proxy.json`
(`{port, pid, started_at}` plus a control token, mode `0600`) and re-attaches.
A proxy from an older build drains its open streams and is replaced once idle.

**Surface.** It binds `127.0.0.1` only, with no option for another interface,
on a fixed port kept in `daemon-config.json`, so the value written into the
agents' files never changes on its own
([The Daemon Binds a Fixed Port and Refuses to Start Without It](daemon-binds-a-fixed-port.md)).
It serves only `POST /anthropic/v1/messages`,
`POST /anthropic/v1/messages/count_tokens`, `GET /anthropic/v1/models`,
`POST /openai/v1/responses` and `HEAD /api/hello`, plus its own control
route; everything else is 404. A request with an `Origin` header or a `Host`
other than the loopback address and port is refused, as the daemon refuses
them ([A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](daemon-auth-and-origin-guard.md)).

**Local token per agent.** Each managed agent has its own random 256-bit
token, compared in constant time, accepted as `Authorization: Bearer` or
`x-api-key`. It unlocks the loopback proxy and nothing else, and it tells the
proxy which agent is calling, which is how usage is attributed. A request
carrying any other credential — a claude.ai OAuth bearer such as
`sk-ant-oat…`, a real provider key — is refused with 401 and nothing is
forwarded. Client credentials are always stripped; the proxy injects the real
key for the upstream it chose. The threat model is stated plainly: the token
keeps browsers and other users' processes out, not a same-user process that
can read what the agent can read, consistent with the principles' "not a
security boundary".

**Pointing the agents.**

- Claude Code, when an API-key connection is active for it:
  `env.ANTHROPIC_BASE_URL = http://127.0.0.1:<port>/anthropic`; `NO_PROXY`
  gains `127.0.0.1,localhost` so a corporate `HTTPS_PROXY` never captures the
  loopback leg; `apiKeyHelper = coffer proxy token --agent-uid <uid>`, which
  prints the agent's local token; the model variables from the agent's
  binding, plus `ANTHROPIC_DEFAULT_HAIKU_MODEL`, because behind a custom base
  URL Claude Code otherwise runs background tasks on the main model, a silent
  cost multiplier its protocol page names.
- Codex: `model_provider = "coffer"` and a `[model_providers.coffer]` table
  with `base_url = http://127.0.0.1:<port>/openai/v1`,
  `wire_api = "responses"`, `supports_websockets = false`,
  `requires_openai_auth = false` and
  `auth = {command = "coffer", args = ["proxy", "token", "--agent-uid", "<uid>"]}`.
  A terminal Codex then works with no export, because it runs the command
  itself. **Version caveat:** the command-backed `auth` table is in Codex's
  current config reference, and the adopting change must confirm it on the
  minimum Codex version Coffer supports before relying on it. On a Codex
  without it, the table falls back to `env_key`, and what that variable
  carries is the agent's local proxy token — never a provider key — injected
  into the Codex processes Coffer spawns and, for terminal use, exported by
  the user.
- `model_catalog_json`, scope-driven reach, one active connection per agent
  type, the boot check and `use-builtin` are unchanged.

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
upstream leg honours the user's `HTTPS_PROXY`.

**Failover.** Only across the keys and endpoints of one connection that serve
the **same model id**, in the same upstream family (Anthropic-direct and a
cloud-hosted Anthropic are not one pool: signatures and cache do not
transfer). A session — `x-claude-code-session-id`, Codex's `session_id` — stays
on one member until that member fails, which keeps the prompt cache warm. A
request fails over only **before the first content byte** reaches the agent:
on a connect, TLS or DNS error, a 5xx, 529 or 429 status, a first-byte
timeout, or an `event: error` that arrives before the first content event
(the proxy holds the response until that point, bounded to a few kilobytes
and seconds). After that it never switches: the error or truncation goes to
the agent and the agent's own retry runs, landing on a healthy member because
the failure has marked this one. The same key is never retried, since both
agents already retry (Codex four request and five stream retries by default),
and a retry storm is what cc-switch recorded before its PR #7426 — nineteen
retries in four minutes against one overloaded upstream. A 429 with
`retry-after` cools its member for that long; 401 or 403 disables the member
until the user fixes it; 400, 404 and 413 never fail over. Mid-stream errors
and truncations count as member failures. There is no model substitution.

**Logging.** Metadata only: the usage record and each failover decision. No
bodies, no prompts, no completions, no credentials; `authorization`,
`x-api-key` and cookies are redacted at the logger, as the audit ADR already
requires of invocation logs.

**Subscription traffic never goes through it.** An agent on its own login has
no proxy base URL and no helper projected, and the proxy refuses the
credential such an agent would send.

- **Pros.** Metering and failover become possible for every API-key request,
  whoever started the agent. The only secret an agent holds is a local token
  that unlocks a loopback relay; the real key never enters an agent's config
  or environment, and the Codex terminal case needs no export. A daemon
  restart or upgrade cuts no stream. Switching between two API-key
  connections changes the proxy's route, not the agent's file.
- **Cons.** A resident process on every API-key model call: if the proxy is
  down, those calls fail until the daemon restarts it. The proxy holds
  decrypted provider keys in memory for its lifetime, which the principles'
  Credentials clause must now name. It sees every prompt in transit, which the
  metadata-only rule keeps out of anything stored. And it is one more process
  to supervise, version and drain on upgrade.
- **Why it wins.** It is the only option that meters and fails over without
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
  ([Usage Is Metered at the Proxy; Subscription Agents Show Only Their Official Remaining Quota](usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota.md)).
- **Why it loses.** It takes on a policy risk and a breakage surface for a
  number that official feeds already provide.

## Decision

An API-key connection reaches Claude Code and Codex through a local model
proxy: a separate process started from the daemon's binary, supervised by the
daemon and surviving its restarts, bound to `127.0.0.1` on a fixed port. Each
agent is pointed at it through its own config — `ANTHROPIC_BASE_URL` plus an
`apiKeyHelper` for Claude Code, a custom `coffer` provider with
`wire_api = "responses"`, WebSockets off and command-based auth for Codex —
and authenticates with a per-agent local token that also attributes its usage.
The proxy relays each request byte for byte to an upstream of the same wire,
reads usage from a copy of the stream, fails over only among members serving
the same model and only before the first content byte, and logs metadata only.
Agents on a subscription login are never pointed at it, and it refuses their
credentials.

This **revises**
[LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md)
in these parts only: its Option B (a local proxy) is adopted, for API-key
connections and in the separate-process form above; the Claude Code writer
projects the proxy's URL, the proxy-token helper, `NO_PROXY` and the pinned
background model instead of the upstream `base_url` and the key helper; the
Codex writer projects the proxy's URL, `supports_websockets = false`,
`requires_openai_auth = false` and the `auth` command instead of the upstream
`base_url` and `env_key`; and a switch between two API-key connections for the
same agent type takes effect in the proxy for sessions opened after the switch
(a running session keeps its route, so thinking signatures stay valid),
without a file rewrite or restart. Its resource model, scope-driven reach,
one-active-per-type rule, boot check, converge re-projection and `use-builtin`
stand; a switch between a subscription login and an API-key connection is
still a file write.

It **revises**
[Provider Keys Never Land in an Agent's Native Config](provider-keys-never-land-in-native-config.md)
in these parts only: its Option C (a proxy that injects the key) is adopted;
the helper `coffer provider key --connection-uid <uid>` and the key route it
calls stop serving agents, replaced by `coffer proxy token --agent-uid <uid>`,
which returns a local token; `COFFER_PROVIDER_KEY` no longer carries a
provider key — it is dropped, or on a Codex without command-backed `auth`
carries the local token — so neither the launch-time injection of a real key
nor the user's terminal export of one remains, and the
`shell_environment_policy` exclude stays only while a token is injected. Its
rule that no raw provider key is ever written into a native config file
stands, and now holds for the agents' environments too.

Rules a future change must respect:

- No protocol translation in 1.0: a route forwards only to an upstream of its
  own wire. Adding translation is a new decision.
- The proxy never forwards a client credential and never accepts one that is
  not a Coffer proxy token.
- Failover never changes the model and never happens after the first content
  byte; the proxy never retries the same key.
- `anthropic-*` headers and body fields are an open list; nothing is
  allow-listed, reordered or re-serialized.
- Nothing the proxy stores or logs contains a body, a prompt, a completion or
  a credential.
- A projection for a subscription-mode agent never writes the proxy URL or
  helper.

## Consequences

- **Principles.** The Credentials clause is amended in the adopting change:
  the proxy holds decrypted provider keys in memory for its lifetime, as a
  header-injection consumer, and never holds the master key. The process
  model — one daemon — gains the proxy as its only sibling process, supervised
  by the daemon.
- **Distribution.** No new binary: the proxy mode ships inside
  `coffer-daemon`, so the three-binary layout of
  [Distribution — Three PyInstaller Binaries](distribution-pyinstaller.md)
  holds, and the release smoke test boots the proxy mode too.
- **Projection.** The provider projection writers move to the proxy form
  through the shared native-config writer and the projection registry; files
  written in the old form are re-projected by the reconciler once, not read
  indefinitely.
- **Tests first.** A byte-equality relay test over recorded SSE, pings
  included; an open-list header test (an unknown `anthropic-beta` value and an
  unknown body field arrive untouched); a failover commit-point test (an error
  before and after the first content byte); auth tests (no token, an
  OAuth-shaped token, a foreign `Host`, an `Origin` present).
- **Obligations.** Spec deltas in provider-switching (the proxy projection,
  the token helper, failover, the refusal of foreign credentials) and daemon
  (supervising and re-attaching to the proxy); the docs-site provider guide
  and architecture pages explain the proxy, the token and what it does not
  log; the minimum Codex version is recorded once the `auth` table is
  confirmed on it.
