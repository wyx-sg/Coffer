# Refresh model prices daily

## Why

Prices change between releases. The bundled genai-prices snapshot alone goes stale until the next
release, so the daemon should keep it fresh the way LiteLLM and genai-prices' own `UpdatePrices`
do, without ever making pricing wait on the network.

## What Changes

- A daemon background worker fetches genai-prices' published `v2/data.json` once shortly after
  start and then every 24 hours: a bounded, read-only GET of one fixed URL.
- The payload is validated and cached atomically at `~/.coffer/derived/genai-prices.json`; pricing
  uses the fresher of the cache and the bundled snapshot. A failure keeps what is there and is
  logged once per failure streak.
- The bundled snapshot moves to the same v2 file, which carries 1-hour cache-write and web-search
  rates.
- A per-machine switch: Settings › General › Refresh model prices, `coffer config set
  prices.refresh`, `GET`/`PUT /api/v1/providers/price-list`; `COFFER_PRICE_REFRESH=off` pins it off.
- "Bundled · updated <date>" on each bundled price, and the Usage dash tooltip names the date.

## Impact

provider-switching spec; `infrastructure/usage/price_refresh.py`; the provider wiring and
shutdown; the CLI config keys; Settings › General, the Models section and Usage; docs-site
providers, usage, security and configuration.
