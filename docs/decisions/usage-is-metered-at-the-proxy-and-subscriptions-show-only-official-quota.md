# Usage Is Metered at the Proxy; Subscription Agents Show Only Their Official Remaining Quota

**Status**: Accepted
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [API-Key Providers Are Reached Through a Separate Local Model Proxy That Relays Bytes Unchanged](api-key-providers-are-reached-through-a-separate-local-model-proxy.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [History Is One SQLite File, `runs.db`, Written Only by the Daemon and Migrated Forward at Startup Through One Alembic Lineage](history-is-one-sqlite-file-written-only-by-the-daemon.md), [Coffer Drives Claude Code Through the Agent SDK and Codex Through `codex app-server`](driving-agents-through-sdk-and-app-server.md), [Audit Every Change With Its Actor, Log Invocations Without Payloads, Prune Per Table](audit-and-retention.md), [Coffer's Agent Hooks Are Marker-Scoped, Explicit, Audited and Repaired When Stale](agent-hook-installation.md), [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), [The Model Catalogue Is Read Back From the Installed Agent](model-catalogue-read-from-the-agent.md), [principles](../../docs-site/architecture/principles.md) (Local-First; Single SQLite writer), research note [credentials and secrets](../research/credentials-secrets.md), research note [provider switching](../research/provider-switching.md), spec provider-switching "Meter every proxied request", spec provider-switching "Show a subscription's official quota as of when it was seen", spec provider-switching "Offer an opt-in statusline wrapper"

## Context

The Usage page answers two different questions for two kinds of agent:

- An agent on an **API-key connection** pays per token. The question is how
  many tokens of which kind it used and what they cost, and since
  [API-Key Providers Are Reached Through a Separate Local Model Proxy](api-key-providers-are-reached-through-a-separate-local-model-proxy.md)
  every such request passes through Coffer's proxy.
- An agent on a **subscription login** (Claude Pro/Max, ChatGPT plans) pays a
  flat fee against rolling windows. The question is how much of the
  five-hour and weekly allowance is left and when it resets — a number only
  the vendor's server knows, since it counts traffic from every device and
  client of the account.

The wire formats decide how tokens are read. On the Anthropic Messages stream,
`message_start.message.usage` carries `input_tokens`,
`cache_creation_input_tokens` (with its `ephemeral_5m` / `ephemeral_1h`
split) and `cache_read_input_tokens`; `message_delta.usage` carries the
cumulative `output_tokens` and may restate and extend the input and cache
totals, because server tools run several sampling iterations. LiteLLM
under-billed exactly there, pricing the `message_start` breakdown and ignoring
the larger final total (BerriAI/litellm #42663). On the OpenAI Responses
stream usage arrives on the terminal `response.completed` (or
`response.incomplete` / `response.failed`): `input_tokens` with
`input_tokens_details.cached_tokens`, `output_tokens` with
`output_tokens_details.reasoning_tokens`. The two conventions differ:
Anthropic's `input_tokens` excludes cache reads and writes, OpenAI's includes
cached tokens, so adding the two naively double-counts. Prices differ per
model and per category, and cache multipliers are model-specific (0.1× on most
models, lower on some), so a single ratio cannot express them.

For subscriptions, research on the installed Claude Code 2.1.281 and Codex
0.155.1 found these feeds:

| Agent | Feed | Status |
| --- | --- | --- |
| Codex | `codex app-server` JSON-RPC `account/rateLimits/read` and the `account/rateLimits/updated` notification — `primary` (about 5 h) and `secondary` (weekly) windows with `used_percent`, `window_duration_mins`, `resets_at` | generated, versioned protocol; not tagged experimental; what Codex's own TUI `/status` calls |
| Claude Code | `rate_limit_event` on the SDK stream of a session Coffer drives | public type (`SDKRateLimitEvent`); its both-windows field `unifiedWindows` is marked `@internal` |
| Claude Code | `rate_limits.five_hour` / `seven_day` (`used_percentage`, `resets_at`) in the statusLine command's stdin JSON | documented (code.claude.com/docs/en/statusline); present only for Pro/Max and after a session's first response |
| Claude Code | SDK control request `get_usage` | shipped as `usage_EXPERIMENTAL_MAY_CHANGE_DO_NOT_RELY_ON_THIS_API_YET` |
| Claude Code | `api.anthropic.com/api/oauth/usage` with the user's OAuth token | undocumented; a request for a documented usage API (anthropics/claude-code #81768) was closed "not planned" |

Anthropic's legal and compliance page (code.claude.com/docs/en/legal-and-compliance,
clarified 2026-02-19) says developers "may not collect, store, or intermediate
Claude.ai credentials or session tokens".

## Options Considered

### Option A — Estimate from local transcripts (the ccusage shape)

Parse `~/.claude/projects/**.jsonl` and `~/.codex/sessions/**.jsonl` for
per-message token counts, price them, and model the five-hour blocks.

- **Pros.** Works offline, for every agent, retroactively; needs no proxy and
  no vendor feed; Coffer already reads transcripts for its history view.
- **Cons.** For API-key traffic it misses every request the agent does not
  write to its transcript (background, compaction, classifier calls) and
  relies on internal file formats. For subscriptions it is a guess: the
  server's allowance counts other devices, the web and mobile apps, and
  weights models in ways the client does not see, so an estimate can say 40 %
  left when the server says 5 %. Tools that do this label the output as an
  estimate for that reason.
- **Why it loses.** The user decided the Usage page shows no estimates for
  subscriptions, and for API-key traffic the proxy sees every request exactly.

### Option B — Read the agent's OAuth token and call the vendor's usage endpoint (the Orca / CodexBar shape)

Take Claude Code's token from the `Claude Code-credentials` Keychain item or
`~/.claude/.credentials.json` and call `/api/oauth/usage`; take Codex's from
`~/.codex/auth.json` and call `chatgpt.com/backend-api/wham/usage`.

- **Pros.** On-demand and complete: every window, per-model scopes, extra
  usage, even with no session running. Orca and CodexBar ship it.
- **Cons.** For Claude it is the collection and intermediation of a
  subscription token that Anthropic's credential policy forbids; Orca also
  sends a spoofed `User-Agent`. The endpoints are undocumented: the query
  flags churn and the response shape has grown several times (Orca carries
  parsers for several variants of the same weekly field). The Claude endpoint
  has a tight budget — Orca's own code notes it answers 429 under polling. On
  macOS, reading another app's Keychain item prompts, the problem Coffer has
  fought since its first credential store. For Codex it means holding a
  secret Coffer does not own when an official RPC returns the same numbers.
- **Why it loses.** Policy, fragility and a secret Coffer has no business
  reading, for data the official feeds already give.

### Option C — Scrape the agents' own `/usage` and `/status` screens in a pseudo-terminal

Spawn the agent hidden, type the command, parse the screen.

- **Pros.** No token handling; the numbers are the ones the user sees.
- **Cons.** UI text changes with most releases; a hidden interactive session
  per refresh; parsing failures look like data.
- **Why it loses.** It is the least robust feed there is, used by others only
  as a last fallback.

### Option D — Ask each provider's billing API for API-key usage

Pull usage from the provider's reporting endpoint.

- **Pros.** The provider's own numbers, including traffic from other tools.
- **Cons.** Anthropic's usage and cost reports need an admin key, not the
  inference key a user registers; relays and resellers expose nothing
  uniform; nothing attributes the traffic to an agent or session; results lag.
- **Why it loses.** It cannot answer "which agent used what", which the proxy
  answers for free.

### Option E — Meter at the proxy; show subscriptions only through official feeds (chosen)

**API-key usage.** The proxy's stream reader writes one record per upstream
attempt: time, agent (from the local token), session and request class where
the agent sends them (`x-claude-code-session-id`, `x-claude-code-agent-id`,
`x-claude-code-request-class`, Codex `session_id`), connection, key alias
(never the key), endpoint, requested model, status, outcome (`completed`,
`error_event`, `truncated`, `client_cancel`), time to first token, duration,
and the normalised token counts. Extraction rules: on Anthropic streams the
last value of each field wins and `message_delta` overrides `message_start`;
on Responses streams the terminal event is read. Normalisation stores
disjoint categories — uncached input, 5-minute cache write, 1-hour cache
write, cache read, output, with reasoning as a part of output — so OpenAI's
`input_tokens` is split into cached and uncached, and Anthropic's is taken as
already uncached. Server-tool counts (web search) and speed or geography
modifiers are kept. A stream cut before its terminal event is recorded with
usage **unknown**, never dropped and never guessed.

**One writer.** The proxy does not open a database. It appends records to a
spool of JSON-lines files under `~/.coffer/proxy-usage/`, part of the runs class
of [Storage Is Five Classes by Nature](storage-is-five-classes-by-nature.md),
and the daemon ingests them into `runs.db` (`usage_requests`, `usage_daily` and
`quota_snapshots`), keeping the single-writer rule. Each row carries
`source = "proxy"` and a de-duplication key — the upstream's request id
(`request-id` / `x-request-id`), or the proxy's own attempt id when the
upstream never answered — so an ingest that repeats after a crash writes
nothing twice, and a later source (a transcript importer, another proxy) can
coexist through the same two columns. Ingest deletes a spool file only after
its rows are committed.

**Cost.** A price is resolved per model and per category (input, output, each
cache write, cache read) plus modifiers (batch, fast mode, geography,
per-request server-tool prices), in this order: the price the user set on the
connection's curated model, a local runtime's, the provider's own API, and a
versioned snapshot bundled with each release (kept fresh by a background
refresh), because relays and resellers price differently from the vendor. A
cache category an override leaves out is charged at its input rate. Cost is
computed at ingest and stored with the label of the price used, so a later table
never rewrites history; the page labels it "estimated", and an unknown model is
flagged rather than priced at zero.

**Subscription quota.** Only the vendor's own remaining allowance, from the
feeds the agent itself publishes:

- **Codex.** `account/rateLimits/read` over `codex app-server` — the client
  Coffer already runs — on page open and manual refresh, and in the
  background no more often than every five minutes (a short-lived app-server
  when no session is live). `account/rateLimits/updated` notifications from
  live Coffer-driven sessions update it between reads. Each window is shown as
  its `used_percent`, labelled by `window_duration_mins`, with `resets_at`. The background read runs only while a Codex agent is on its own
  login, and a manual refresh is floored at 30 seconds.
- **Claude Code.** `rate_limit_event` from every session Coffer drives,
  reading the both-windows field when present and the top-level window
  otherwise, so its `@internal` status degrades to less detail, not to a
  failure. An **opt-in** statusline integration covers the user's own
  terminal sessions: `coffer usage statusline -- <command>` forwards the
  documented `rate_limits` object to the daemon and then runs the user's
  original `statusLine` command with the same input, printing its output — it
  chains, never replaces, and runs the original even when the daemon is down.
  Coffer never installs it: the edit is to a setting of Claude Code's that
  differs per person, so it is handed to the person's agent as a prompt that
  asks for no credential and no quota endpoint.
  The experimental `get_usage` request is not used.
- Every value is shown "as of <time>" from the moment its source produced it.
  With no fresh value there is no number: the page says when the last one
  was seen, or that none has been.

Coffer never reads another application's OAuth token or credential file and
never calls an undocumented quota endpoint.

- **Pros.** API-key usage is exact per request and attributed per agent and
  session, including requests transcripts never show; costs are reproducible
  from a stored price version; subscription numbers are the server's own and
  come without touching a token; every feed but `get_usage` is documented or
  generated.
- **Cons.** Claude Code quota exists only while some session runs — a user
  who never lets Coffer drive a session or enable the statusline sees
  nothing; the statusline needs the user's single `statusLine` slot; the
  both-windows field may disappear; usage exists only for traffic through the
  proxy, not for requests made before it or by other tools on the same key.
- **Why it wins.** It is the only option that is exact for API-key traffic,
  truthful for subscriptions and inside Anthropic's credential policy.

## Decision

Usage of API-key traffic is recorded by the proxy per upstream attempt, with
tokens extracted by per-wire rules (the final `message_delta` overriding
`message_start`; the terminal Responses event) and normalised into disjoint
categories; the proxy spools the records and the daemon, the only writer,
ingests them into `runs.db` with a `source` and a de-duplication key. Cost is
computed at ingest from per-model, per-category prices (a connection's own
override first, a bundled versioned snapshot last), and stored with the label
of the price used.

A subscription agent shows only its official remaining quota: for Codex from
app-server's `account/rateLimits/read` and its `updated` notification; for
Claude Code from `rate_limit_event` on Coffer-driven sessions and an opt-in
opt-in statusline wrapper that forwards `rate_limits` and chains the user's own
command; always labelled "as of <time>".

Rules a future change must respect:

- No estimate is ever shown as a subscription's remaining quota.
- Coffer never reads another application's OAuth token or credential store,
  and never calls an undocumented quota endpoint.
- A usage row without a `source` and a de-duplication key is a defect; an
  incomplete stream is recorded as unknown, not zero.
- Stored cost always names the price it used.

## Consequences

- **Storage.** `runs.db` holds the usage records (`usage_requests`, per-request
  detail kept for the MCP invocation log's retention window) and daily totals
  (`usage_daily`, kept 365 days), and the quota snapshots; the spool is a
  runs-class directory the daemon empties; retention prunes usage like the other
  run tables ([Audit Every Change With Its Actor](audit-and-retention.md)).
- **Agents.** The Codex app-server client has one request and one notification;
  the Claude SDK mapping surfaces `rate_limit_event` instead of dropping it;
  the statusline wrapper is a command the user opts into, never a Coffer-managed
  entry in `~/.claude/settings.json`.
- **Prices.** The bundled snapshot carries Anthropic's first-party rates only;
  other vendors' models are unpriced until the user sets a price on the
  connection's curated model or the provider's API supplies one.
- **Tests.** Parser golden files (a `message_delta` overriding `message_start`,
  server-tool iterations, Responses cached and reasoning tokens, a truncated
  stream); an ingest replay that writes nothing twice; a statusline test that the
  user's original command still runs with the daemon down.
- The architecture page [The local model proxy](../../docs-site/architecture/model-proxy.md)
  and the Usage guide say where each number comes from and why a subscription
  number can be missing.
