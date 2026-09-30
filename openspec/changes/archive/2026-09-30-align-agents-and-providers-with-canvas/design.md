# Design

## Price resolution

One resolver (`application/provider/prices.py`) answers both "what did this request cost" (usage
ingest) and "what does this model cost here" (the Models section), so the two never disagree.

- **You set** is the curated model's `price` (already stored on the connection).
- **Local** runtimes are free. This precedes the provider and bundled sources so a local
  `gpt-oss-20b` is never priced as OpenAI's.
- **From <provider>**: the OpenAI-compatible `/models` listing is read for OpenRouter's `pricing`
  object (per-token strings, converted to per 1M). The prices are kept in
  `~/.coffer/derived/reported-prices.json`, keyed by the endpoint root, written only when a listing
  reports some. It is derived state: never synced, rebuilt by the next listing.
- **Bundled**: pydantic/genai-prices is MIT; its data file is vendored at
  `backend/coffer/infrastructure/usage/price_list/genai-prices.json` (slimmed to the fields pricing
  reads) with its licence beside it, and refreshed by `make refresh-prices` at release time. The
  provider is chosen by matching the connection's base URL against each provider's `api_pattern`,
  else by the model's vendor (`model_match`), as genai-prices does; `fallback_model_providers` is
  followed one step. Conditional (historical, time-of-day) prices are chosen by the request's start
  time; tiers are cliffs on total input tokens. Coffer's own Anthropic table remains as a supplement
  for models the list has not caught up with; it wins only when the list reaches the model through
  a broader prefix rather than naming it.

The stored label changes from `snapshot:<version>` to `bundled:genai-prices@<commit>+coffer@<date>`;
old rows keep theirs.

## Failover order and switch

The order is a `position` on each connection's config (omitted until placed), so it syncs with the
connection and needs no migration; unplaced connections sort by name after placed ones, which keeps
the previous alphabetical behaviour. `fallback` (default true, omitted when true) is read when the
proxy state is built. The proxy's hot path is unchanged: the route's members are simply built in
list order, without providers switched off.

The UI's "If X fails: Y" reads the same state the proxy is pushed (`ProxyFacade.state`), so it only
names providers that are really eligible (enabled, keyed, approved, offering the model).

## Failover log

The proxy has no database. Each usage record now carries a `relay_id` shared by every attempt at one
request; on ingest, each record with `failed_over` becomes a `provider_failover` audit row naming the
next attempt of the same request found in the same file. A replayed file inserts no rows and logs
nothing.
