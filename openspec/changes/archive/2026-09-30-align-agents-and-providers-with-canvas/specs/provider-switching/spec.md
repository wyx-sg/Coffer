## RENAMED Requirements

- FROM: `### Requirement: Price usage from a bundled snapshot and per-connection prices`
- TO: `### Requirement: Resolve each model's price from the provider, its API, or the bundled list`

## MODIFIED Requirements

### Requirement: Resolve each model's price from the provider, its API, or the bundled list
Cost MUST be estimated at ingest, per model and per token category, at the price resolved for the
connection that served the request, in this order: (1) the price the user set on that connection
for the model ("You set" — relays and resellers price differently); (2) a model runtime on this
machine costs nothing; (3) the price the connection's own API reported when its models were last
listed or refreshed (OpenRouter-style `/models` pricing), remembered in a derived store and never
fetched per request; (4) the price list bundled with the release — pydantic/genai-prices (MIT),
provider-scoped by the connection's base URL (an endpoint no provider claims is priced as the
model's vendor), with historical prices by the request's start time, tiered prices by the
request's total input tokens, and cache read and write rates — supplemented by Coffer's own
Anthropic rates for models the list has not caught up with. Coffer MUST NOT look prices up over the
network at runtime; the bundled list is refreshed at release time (`make refresh-prices`). Each
cost MUST be stored with the label of the price it used (`override:<connection uid>`,
`provider:<connection uid>`, `bundled:<list version>` or `local`) so a later list never rewrites
history. A cache category a price leaves out is charged at its input rate. A model none of them
prices MUST be marked unpriced, never costed at zero. `POST /api/v1/providers/{uid}/prices`
resolves the same prices for the Models section, each with its source; `coffer provider price
<name> [<model> --input <usd> --output <usd> | --reset]` shows them and sets or resets the price
the user records. Every surface labels cost as estimated. Where nothing in a cost is priced, the web
UI and the CLI MUST show `—` in its place, never `$0.00`, and the web UI MUST say why and where a
price is set in the dash's tooltip and accessible name. Subscription logins are not metered and show
only their official quota.

#### Scenario: a known model is priced per category
- **GIVEN** a record for `claude-sonnet-4-6` through `https://api.anthropic.com` with input, cache-write, cache-read and output tokens
- **WHEN** it is priced
- **THEN** each category is charged at that model's own rate from the bundled list

#### Scenario: an unknown model is marked unpriced, never zero
- **GIVEN** a record for a model no connection price, provider API or bundled list prices
- **WHEN** it is priced
- **THEN** it has no cost and is marked unpriced

#### Scenario: stored cost names the price it used
- **GIVEN** one record priced from the bundled list and one from its connection's own price
- **WHEN** both are ingested
- **THEN** each row names the price it was costed with

#### Scenario: a price is taken from the first source that has one
- **GIVEN** a connection with its own price for one model, a price its API reported for a second, the bundled list's price for a third, and a local runtime connection
- **WHEN** each model's price is resolved
- **THEN** the first reads You set, the second From the connection, the third Bundled, and the local runtime's model costs nothing

#### Scenario: each price names where it came from
- **GIVEN** a provider whose models are priced from different sources, and one model nothing prices
- **WHEN** its Models section renders
- **THEN** each priced model shows its input and output price per 1M tokens with You set, From <provider> or Bundled, and the unpriced one shows `—` with Set price…

#### Scenario: a model with no price reads as a dash, never zero
- **GIVEN** usage of a model through a connection that records no price for it, whose API reported none, and that the bundled list does not know
- **WHEN** the Usage page and `coffer usage` show that model's row
- **THEN** its cost reads `—`, not `$0.00`, with the unpriced request count
- **AND** on the Usage page the dash's tooltip says no price is known for it and that a price is set in Model providers

### Requirement: Fail over only before the first content byte
When a request fails before the first content byte reaches the agent — a connect, TLS or DNS
error, a 5xx, 529 or 429 status, a 401 or 403, a first-byte timeout, or an error event before the
first content event (the proxy holds the response until then, bounded to 64 KiB and 5 seconds) — the proxy MUST move it to the next member of the agent's route: another enabled
connection that reaches the same agent type, speaks the same protocol, is switched on as a fallback
and lists the requested model among its curated models, tried in the Model providers list order
(see "Order providers, and fail over in that order"). Failover MUST never change the model, never
try the same member twice for one request, and never happen after the first content byte: an error
or truncation after it goes to the agent, whose own retry lands on a healthy member. A 429 with
`retry-after` cools that member for that long; 401 or 403 disables it until its key changes; 400,
404 and 413 are relayed and never fail over. A local runtime connection has no fallback members and
is never a fallback. A session stays on one member until that member fails.

#### Scenario: a failure before the first byte moves to another connection serving the model
- **GIVEN** an agent's active connection answering 503, and another connection reaching the agent that lists the requested model
- **WHEN** the agent sends a request
- **THEN** the agent receives the second connection's response and never sees the 503

#### Scenario: an error after the first content byte is passed to the agent
- **GIVEN** an active connection whose stream fails after its first content event
- **WHEN** the agent sends a streaming request
- **THEN** the agent receives the partial stream and the error, and no other connection is tried

#### Scenario: a request problem is never failed over
- **GIVEN** an active connection answering 400
- **WHEN** the agent sends a request
- **THEN** the 400 and its body reach the agent unchanged and no other connection is tried

#### Scenario: failover never changes the model
- **GIVEN** an active connection answering 529, a second connection that does not list the requested model, and a third that does
- **WHEN** the agent sends a request
- **THEN** the second connection is never tried, and the third receives the request with the model the agent asked for

## ADDED Requirements

### Requirement: Order providers, and fail over in that order
The Model providers list MUST have an order the user sets, and that order MUST be the order the
proxy tries fallbacks in: the agent's own connection first, then the other eligible connections in
list order. The order is saved as each connection's position (`PUT /api/v1/providers/order` with
every connection's uid exactly once, else 422; `coffer provider order <name>…` puts the named ones
first); a connection never placed sorts after the placed ones, by name. The list offers a drag
handle on each row, moves with the keyboard, and explains in its help that order is fallback
priority. Each connection MUST carry **Use as fallback for other providers** (`fallback`, on by
default; `PATCH /api/v1/providers/{uid}`, `coffer provider edit --fallback|--no-fallback`): switched
off, it is never tried for another connection's request, though its own agents still fail over from
it. A local runtime is never a fallback and its detail says so. The agent's Model tab MUST show,
read-only, where its requests go next — "If <provider> fails: <fallbacks>" or "No fallback" — from
`GET /api/v1/proxy/routes/{agent_uid}?model=<model>`, and the last four characters of the agent's
own proxy token (`GET /api/v1/proxy/tokens/{agent_uid}/hint`) with Rotate. Usage is metered on the
connection that actually answered.

#### Scenario: fallbacks are tried in the Model providers list order
- **GIVEN** an agent on connection A and connections B and C that also offer its model, listed C, A, B
- **WHEN** the proxy's route for the agent is built
- **THEN** it tries A, then C, then B

#### Scenario: a provider switched off as a fallback is never failed over to
- **GIVEN** an agent on connection A and connection B offering the same model with Use as fallback for other providers switched off
- **WHEN** the proxy's route for the agent is built
- **THEN** it holds A only

#### Scenario: the Model tab says which provider is tried next
- **GIVEN** an agent on a connection whose model a second connection also offers
- **WHEN** the agent's Model tab renders
- **THEN** it reads "If <its provider> fails: <the second>" and shows the agent's proxy token by its last four characters with Rotate

### Requirement: Log every failover in Activity
Every attempt the proxy moves off a connection before the first byte MUST be recorded in the audit
log as `provider_failover`, filed against the connection it left, with the agent, the model, the
reason (the status or the failure) and — when the same request's next attempt is in the same spool
file — the connection it went to. The Activity page shows it as a sentence. A spool file ingested a
second time logs nothing twice. Reordering the list is recorded as `provider_reordered`.

#### Scenario: a failover is logged with where the request went
- **GIVEN** a request whose first attempt failed over with 503 and whose second attempt was answered by another connection
- **WHEN** the daemon ingests the spool file
- **THEN** one `provider_failover` names the connection it left, the one that answered, the model and the status
- **AND** the answering connection's attempt carries the request's usage and cost
