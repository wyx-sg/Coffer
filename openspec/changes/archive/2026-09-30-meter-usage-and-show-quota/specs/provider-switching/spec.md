## ADDED Requirements

### Requirement: Meter every proxied request
The local model proxy MUST record one usage record per upstream attempt of a Messages or Responses
request, failed-over attempts included: when it started, the agent (from its local token), the
session and request class where the agent sends them, the connection, the endpoint, the requested
model, the status, the outcome (`completed`, `error_event`, `truncated`, `client_cancel`,
`upstream_error`, `connect_error`), the time to first token, the duration, and the tokens in
disjoint categories — uncached input, 5-minute and 1-hour cache writes, cache reads, output (with
reasoning as a part of output), and web-search requests. On the Anthropic wire the last value of each
field wins and `message_delta` overrides `message_start`; on the Responses wire the terminal event
carries them and cached tokens are split out of `input_tokens`; a non-streamed body is read the same
way. A stream cut before its terminal event MUST be recorded with usage unknown — never dropped and
never guessed. The proxy opens no database: it spools records to `~/.coffer/proxy-usage/`, and the
daemon ingests completed files into its database with `source = "proxy"` and a de-duplication key
(the upstream's request id, else the proxy's attempt id), deleting a file only after its rows are
committed, so a repeated ingest writes nothing twice. No record carries a body, a prompt, a
completion or a credential. How the proxy reads the stream is
[The local model proxy](../../../docs-site/architecture/model-proxy.md).

#### Scenario: a streamed request is recorded with its tokens by category
- **GIVEN** an agent's Responses request whose stream reports 1000 input tokens of which 600 cached, and 90 output tokens of which 40 reasoning
- **WHEN** the proxy relays it
- **THEN** the record carries 400 uncached input, 600 cache-read and 90 output tokens with 40 reasoning, the agent, the connection, the upstream's request id as its de-duplication key and the outcome `completed`

#### Scenario: the final message_delta overrides message_start
- **GIVEN** an Anthropic stream whose `message_delta` restates larger input and cache totals than its `message_start`
- **WHEN** its usage is read
- **THEN** the record carries the `message_delta` totals

#### Scenario: a stream cut short is recorded as unknown
- **GIVEN** an Anthropic stream that ends before `message_stop`
- **WHEN** its usage is read
- **THEN** the usage is marked unknown and no token count is invented

#### Scenario: nothing stored carries a body or a key
- **GIVEN** a request whose prompt and whose connection key are known strings
- **WHEN** the proxy relays and spools it
- **THEN** neither string appears in the spooled record

#### Scenario: replaying a spool file writes nothing twice
- **GIVEN** a spool file the daemon has ingested
- **WHEN** the same records are ingested again
- **THEN** no usage row or daily total changes

### Requirement: Keep usage detail for the invocation window and daily totals for a year
Per-request usage rows MUST follow the MCP invocation log's retention policy (`mcp_invocations`,
30 days by default): they have no policy of their own, and changing that window changes theirs.
Daily totals — per day, agent, connection and model — MUST be kept for 365 days under their own
policy. Both are pruned on the retention cadence.

#### Scenario: request detail follows the MCP calls window
- **GIVEN** usage rows older and newer than the MCP invocation window
- **WHEN** retention prunes
- **THEN** the older rows are gone, the newer remain, and the daily totals are untouched

### Requirement: Price usage from a bundled snapshot and per-connection prices
Cost MUST be estimated at ingest, per model and per token category, from a versioned price snapshot
shipped with the release, unless the connection records its own price for that model (relays and
resellers price differently), and stored with the price it used (`snapshot:<version>` or
`override:<connection uid>`) so a later snapshot never rewrites history. A cache category an
override leaves out is charged at its input rate. A model neither prices MUST be marked unpriced,
never costed at zero. The snapshot carries Anthropic's first-party rates; other vendors' models are
unpriced until the user sets a price on the connection. Every surface labels cost as estimated.

#### Scenario: a known model is priced per category
- **GIVEN** a record for `claude-opus-5-5` with input, cache-write, cache-read and output tokens
- **WHEN** it is priced
- **THEN** each category is charged at that model's own rate

#### Scenario: an unknown model is marked unpriced, never zero
- **GIVEN** a record for a model no snapshot or connection prices
- **WHEN** it is priced
- **THEN** it has no cost and is marked unpriced

#### Scenario: stored cost names the price it used
- **GIVEN** one record priced from the snapshot and one from its connection's own price
- **WHEN** both are ingested
- **THEN** each row names the price it was costed with

### Requirement: Report usage by model, agent or day over a range
`GET /api/v1/usage/summary` and `coffer usage [--range today|7d|30d|month|custom] [--from <day> --to <day>] [--by model|agent|day] [--json]`
MUST report, for the range in the machine's local days (today; the last 7 or 30 days including today;
this calendar month; or an inclusive custom range), one row per model (with the connection that
served it, by uid and name), per agent or per day: requests, the token totals per category, the
estimated cost, and how many requests were unpriced or had unknown usage. `GET /api/v1/usage/requests`
and `coffer usage requests` page through the per-request detail, newest first.
`GET /api/v1/usage/export.csv` and `coffer usage --csv` return the same summary as CSV.

#### Scenario: usage by model names the connection
- **GIVEN** usage of two models over two connections
- **WHEN** the summary is grouped by model
- **THEN** each row names its model and the connection's uid and name, with its requests, tokens and estimated cost

#### Scenario: usage by agent and by day
- **GIVEN** usage by two agents on two days
- **WHEN** the summary is grouped by agent, and then by day
- **THEN** it returns one row per agent, and then one row per day

#### Scenario: a range resolves in local days
- **GIVEN** a clock on a known local day
- **WHEN** the ranges today, 7d, 30d and this month are resolved
- **THEN** each spans the local days it names, today included

#### Scenario: export usage as CSV
- **GIVEN** usage in the range
- **WHEN** the user exports it
- **THEN** the CSV has a header row and one line per group with the same totals the summary reports

### Requirement: Show a subscription's official quota as of when it was seen
For an agent on its own subscription login, Coffer MUST show only the vendor's own remaining
allowance, never an estimate, each window with its used percentage, its length and when it resets,
labelled with when its source produced it. Codex's comes from `codex app-server`'s
`account/rateLimits/read` — on request (`POST /api/v1/usage/quota/refresh`, `coffer usage quota
--refresh`), and in the background no more often than every five minutes while a Codex agent is on its
own login — and from `account/rateLimits/updated` notifications of the sessions Coffer drives.
Claude Code's comes from the `rate_limit_event` of the sessions Coffer drives, preferring its
both-windows field and degrading to the top-level window when that is absent. Coffer MUST NOT read
another application's OAuth token or credential file and MUST NOT call an undocumented quota
endpoint. `GET /api/v1/usage/quota` and `coffer usage quota` report the latest window per agent type;
with no value, or a window whose reset has passed, they say so and show no number.

#### Scenario: Codex quota comes from its app-server
- **GIVEN** a `codex app-server` that answers `account/rateLimits/read` with a primary and a secondary window
- **WHEN** Coffer reads Codex's quota
- **THEN** both windows are stored with their used percentage, length, reset time and when they were seen

#### Scenario: Claude Code quota comes from a driven session's rate-limit event
- **GIVEN** a Claude Code session Coffer drives that emits a `rate_limit_event`
- **WHEN** the event arrives
- **THEN** its windows are stored as Claude Code's quota, and the turn is unaffected

#### Scenario: no fresh value shows no number
- **GIVEN** an agent type no source has reported for, and a window whose reset time has passed
- **WHEN** the quota is read
- **THEN** the first says no value has been seen and the second shows no percentage

#### Scenario: Codex is not read more often than every five minutes
- **GIVEN** a Codex quota read a minute ago
- **WHEN** the background loop asks again, and then a manual refresh asks within thirty seconds
- **THEN** neither reaches the app-server

### Requirement: Offer an opt-in statusline wrapper
`coffer usage statusline -- <the user's own statusLine command>` MUST forward the `rate_limits`
object of the statusline JSON Claude Code writes to its stdin to
`POST /api/v1/usage/quota/statusline`, with a timeout of at most one second and never starting a
daemon, then run the user's own command with the same stdin and print its output and exit code —
even when the daemon is down. Coffer never installs it: the user opts in by setting it as their
`statusLine` command, which covers the Claude Code sessions they run in their own terminal.

#### Scenario: the user's statusline command still runs with the daemon down
- **GIVEN** no daemon running
- **WHEN** Claude Code runs the wrapper with the user's own statusline command
- **THEN** the user's command runs with the same stdin and its output is printed
