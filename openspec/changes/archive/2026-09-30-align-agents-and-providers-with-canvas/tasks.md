# Tasks

## Prices
- [x] Vendor pydantic/genai-prices with its licence; `scripts/refresh_model_prices.py`, `make refresh-prices`, RELEASING step; ship it in the daemon build
- [x] Bundled catalogue: provider scope, conditional and tiered prices, cache rates, Coffer's supplement
- [x] Remember prices reported by a provider's `/models` listing
- [x] One resolver for ingest and the Models section; `POST /providers/{uid}/prices`
- [x] `coffer provider price`
- [x] Models section: price and source tag per model, Set price…, Reset; Usage tooltip copy

## Failover
- [x] `position` and `fallback` on the connection; `PUT /providers/order`; `coffer provider order`, `edit --fallback`
- [x] Proxy routes built in list order without providers switched off
- [x] `relay_id` on usage records; `provider_failover` and `provider_reordered` audit events, Activity labels
- [x] `GET /proxy/routes/{agent_uid}`, `GET /proxy/tokens/{agent_uid}/hint`
- [x] Reorderable list with help; Fallback switch on the Endpoint; Model tab Fallback and Proxy token rows

## Pages
- [x] Model providers detail without tabs; old `/models` links redirect
- [x] Agents detail: Repair wording, hook not approved, Untrusted panel, row menus, skill delete, Config files new/delete/guard
- [x] Model tab copy says provider

## Docs
- [x] docs-site, coffer-guide, generated references
