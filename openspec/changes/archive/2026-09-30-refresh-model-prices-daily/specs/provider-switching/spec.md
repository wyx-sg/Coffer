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
Anthropic rates for models the list has not caught up with. The bundled snapshot is refreshed at
release time (`make refresh-prices`), and between releases the daemon refreshes it once a day (see
"Refresh the bundled price list in the background"); whichever copy is fresher is used, and no
price is ever looked up over the network per request or while a request is being costed. Each
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
- **THEN** each priced model shows its input and output price per 1M tokens with You set, From <provider> or Bundled · updated <the date of the list in use>, and the unpriced one shows `—` with Set price…

#### Scenario: a model with no price reads as a dash, never zero
- **GIVEN** usage of a model through a connection that records no price for it, whose API reported none, and that the bundled list does not know
- **WHEN** the Usage page and `coffer usage` show that model's row
- **THEN** its cost reads `—`, not `$0.00`, with the unpriced request count
- **AND** on the Usage page the dash's tooltip says no price is known for it and that a price is set in Model providers

## ADDED Requirements

### Requirement: Refresh the bundled price list in the background
Besides the snapshot shipped in the build, the daemon MUST refresh the model price list from the
file pydantic/genai-prices publishes — the one its own `UpdatePrices` fetches,
`https://raw.githubusercontent.com/pydantic/genai-prices/refs/heads/main/prices/new_data/v2/data.json`,
a fixed URL Coffer chose, never one a user typed — once shortly after it starts and then every
24 hours. The fetch MUST be a read-only `GET` with a timeout and a size cap that sends nothing about
the user. The payload MUST be validated (a provider array that parses, with Anthropic and OpenAI in
it) before it is kept, and cached atomically at `~/.coffer/derived/genai-prices.json` with when it
was fetched. Pricing MUST use whichever of the cache and the bundled snapshot is fresher, and MUST
never wait on the network: a failed fetch keeps the list in use and is logged once per run of
failures, not on every attempt. The refresh is on by default and is switched per machine —
**Refresh model prices** in Settings › General under Coffer's model, `coffer config set
prices.refresh on|off`, `PUT /api/v1/providers/price-list` — and `COFFER_PRICE_REFRESH=off` pins it
off. `GET /api/v1/providers/price-list` says which list is in use, the day its data is from, and
the refresh's state; a bundled price reads "Bundled · updated <that day>", and the Usage page's
dash tooltip names the same day.

#### Scenario: a refreshed list is cached and used
- **GIVEN** the published list prices a model differently from the bundled snapshot
- **WHEN** the refresh runs
- **THEN** the list is cached with when it was fetched, the model is priced from it, and a daemon started later uses the cache without fetching

#### Scenario: a failed refresh keeps the list in use
- **GIVEN** a refreshed list in use
- **WHEN** the next two refreshes fail, one unreachable and one returning something that is not a price list
- **THEN** the list in use and its cache are unchanged, and the failure is logged once

#### Scenario: the fresher of the cache and the bundled list is used
- **GIVEN** a cached list older than the bundled snapshot, and another newer than it
- **WHEN** a price is looked up with each
- **THEN** the older cache gives way to the bundled snapshot and the newer cache is used

#### Scenario: the refresh can be turned off
- **GIVEN** Refresh model prices turned off
- **WHEN** the refresh's schedule comes round
- **THEN** nothing is fetched and prices come from the bundled snapshot
