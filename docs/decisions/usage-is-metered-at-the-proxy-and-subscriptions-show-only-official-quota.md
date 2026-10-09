# Usage Is Metered at the Proxy; Subscription Agents Are Not Metered

**Status**: Accepted
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [API-Key Providers Are Reached Through a Separate Local Model Proxy That Relays Bytes Unchanged](api-key-providers-are-reached-through-a-separate-local-model-proxy.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [History Is One SQLite File, `runs.db`, Written Only by the Daemon and Migrated Forward at Startup Through One Alembic Lineage](history-is-one-sqlite-file-written-only-by-the-daemon.md), [Audit Every Change With Its Actor, Log Every Invocation, Prune Per Table](audit-and-retention.md), [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), [The Model Catalogue Is Read Back From the Installed Agent](model-catalogue-read-from-the-agent.md), [principles](../../docs-site/architecture/principles.md) (Local-First; Single SQLite writer), research note [credentials and secrets](../research/credentials-secrets.md), research note [provider switching](../research/provider-switching.md), spec provider-switching "Meter every proxied request", spec provider-switching "Show metered usage on a Usage tab of Model providers"

## Context

Usage answers one question: how many tokens of which kind an agent used, and
what they cost. It can answer it exactly for an agent on an **API-key or
local provider**, because since
[API-Key Providers Are Reached Through a Separate Local Model Proxy](api-key-providers-are-reached-through-a-separate-local-model-proxy.md)
every such request passes through Coffer's proxy.

An agent on a **subscription login** (Claude Pro/Max, ChatGPT plans) pays a flat
fee against rolling windows, and the question that matters there is how much of
the five-hour and weekly allowance is left. Only the vendor's server knows it:
it counts traffic from every device and client of the account, and none of that
traffic reaches Coffer.

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

Subscription quota was weighed too, and its sources are what decide it. Codex
publishes the numbers over `codex app-server` (`account/rateLimits/read`);
Claude Code publishes them only as a `rate_limit_event` on the stream of a
session Coffer itself drives and, documented, in the stdin of a user's
`statusLine` command. Anthropic's legal and compliance page
(code.claude.com/docs/en/legal-and-compliance, clarified 2026-02-19) says
developers "may not collect, store, or intermediate Claude.ai credentials or
session tokens", which rules out calling the vendor's usage endpoint with the
agent's own token.

## Options Considered

### Option A — Estimate from local transcripts (the ccusage shape)

Parse `~/.claude/projects/**.jsonl` and `~/.codex/sessions/**.jsonl` for
per-message token counts, price them, and model the five-hour blocks.

- **Pros.** Works offline, for every agent, retroactively; needs no proxy and
  no vendor feed.
- **Cons.** For API-key traffic it misses every request the agent does not
  write to its transcript (background, compaction, classifier calls). For
  subscriptions it is a guess: the server's allowance counts other devices and
  weights models in ways the client does not see, so an estimate can say 40 %
  left when the server says 5 %.
- **Why it loses.** An estimate must never stand for a subscription's remaining
  allowance, and for API-key traffic the proxy sees every request exactly.

### Option B — Read the agent's OAuth token and call the vendor's usage endpoint

Take Claude Code's or Codex's token from its keychain item or credential file
and call the vendor's undocumented usage endpoint.

- **Pros.** On-demand and complete, even with no session running.
- **Cons.** For Claude it is the collection and intermediation of a
  subscription token that Anthropic's credential policy forbids; the endpoints
  are undocumented and churn; and reading another app's keychain item prompts
  the person, the problem Coffer has fought since its first credential store.
- **Why it loses.** Policy, fragility and a secret Coffer has no business
  reading.

### Option C — Scrape the agents' own `/usage` and `/status` screens

Spawn the agent hidden in a pseudo-terminal, type the command, parse the
screen.

- **Cons.** UI text changes with most releases; a hidden interactive session per
  refresh; parsing failures look like data.
- **Why it loses.** It is the least robust feed there is.

### Option D — Ask each provider's billing API for API-key usage

- **Cons.** Anthropic's usage and cost reports need an admin key, not the
  inference key a person registers; relays and resellers expose nothing
  uniform; nothing attributes the traffic to an agent or session; results lag.
- **Why it loses.** It cannot answer "which agent used what", which the proxy
  answers for free.

### Option E — Relay the vendor's official feeds (tried first, dropped)

Show a subscription's quota from the feeds above: Codex's app-server RPC
(background reads while a Codex agent was on its own login), Claude Code's
`rate_limit_event` from sessions Coffer drives, and an opt-in `statusLine`
wrapper (`coffer usage statusline`) for the person's own terminal sessions,
each value labelled "as of <time>".

- **Pros.** The numbers are the server's own and come without touching a token.
- **Cons.** The reading covers only part of a person's use. A Claude Code agent
  used from the person's own terminal showed nothing unless they gave up their
  single `statusLine` slot to a wrapper edited into Claude Code's settings.
  Claude's both-windows field is marked `@internal`. Codex needed a short-lived
  `codex app-server` spawned in the background every few minutes. All of it
  for a number the vendor's own app already shows.
- **Why it lost.** The finished Usage design dropped it: a half-complete quota
  that needs a settings edit is worse than none, and what is left (cost and
  tokens of requests through Coffer) belongs beside the providers those
  requests went through.

### Option F — Meter at the proxy; do not meter subscription agents (chosen)

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
and the daemon ingests them into `runs.db` (`usage_requests` and
`usage_daily`), keeping the single-writer rule. Each row carries
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

**Subscriptions.** An agent on its own login never passes through the proxy, so
Coffer meters nothing for it and shows no quota, no estimate and no
placeholder for one. The person reads the allowance in the vendor's own app.
Coffer never reads another application's OAuth token or credential file and
never calls an undocumented quota endpoint.

- **Pros.** API-key usage is exact per request and attributed per agent and
  session, including requests transcripts never show; costs are reproducible
  from a stored price version; nothing touches a token or edits another
  tool's settings.
- **Cons.** Usage exists only for traffic through the proxy, not for requests
  made before an agent was switched onto the provider or by other tools on the
  same key; a subscription's remaining allowance is not shown at all.
- **Why it wins.** It is the only option that is exact for API-key traffic and
  stays inside Anthropic's credential policy, and it asks nothing of the person.

## Decision

Usage of API-key traffic is recorded by the proxy per upstream attempt, with
tokens extracted by per-wire rules (the final `message_delta` overriding
`message_start`; the terminal Responses event) and normalised into disjoint
categories; the proxy spools the records and the daemon, the only writer,
ingests them into `runs.db` with a `source` and a de-duplication key. Cost is
computed at ingest from per-model, per-category prices (a connection's own
override first, a bundled versioned snapshot last), and stored with the label
of the price used.

A subscription agent is not metered: Coffer shows no quota for it.

Rules a future change must respect:

- No estimate is ever shown as a subscription's remaining quota, and Coffer
  never reads another application's OAuth token or credential store or calls
  an undocumented quota endpoint.
- A usage row without a `source` and a de-duplication key is a defect; an
  incomplete stream is recorded as unknown, not zero.
- Stored cost always names the price it used.

## Consequences

- **Storage.** `runs.db` holds the usage records (`usage_requests`, per-request
  detail kept for the MCP invocation log's retention window) and daily totals
  (`usage_daily`, kept 365 days); the spool is a
  runs-class directory the daemon empties; retention prunes usage like the other
  run tables ([Audit Every Change With Its Actor](audit-and-retention.md)).
- **Prices.** The bundled snapshot carries Anthropic's first-party rates only;
  other vendors' models are unpriced until the user sets a price on the
  connection's curated model or the provider's API supplies one.
- **Tests.** Parser golden files (a `message_delta` overriding `message_start`,
  server-tool iterations, Responses cached and reasoning tokens, a truncated
  stream); an ingest replay that writes nothing twice.
- The architecture page [The local model proxy](../../docs-site/architecture/model-proxy.md)
  and the Usage guide say where each number comes from and that a subscription
  agent is not metered.
