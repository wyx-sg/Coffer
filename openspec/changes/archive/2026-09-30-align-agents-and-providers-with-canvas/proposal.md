# Align Agents and Model providers with the canvas

## Why

The canvas for ② Agents settles three things the code does not do yet: where a model's price comes
from and how that is shown, how failover between providers is ordered and switched, and a Model
providers detail with no tabs. Several Agents boards also show states and actions the pages lack.

## What Changes

- **Prices.** A model's price on a provider is resolved in one order — You set, a local runtime
  (free), the provider API's reported price (captured when models are listed), the bundled list
  (pydantic/genai-prices, provider-scoped, historical and tiered, with cache rates, refreshed at
  release time by `make refresh-prices`) — or none, shown as "—". The usage meter and the Models
  section use the same resolver. `POST /api/v1/providers/{uid}/prices`, `coffer provider price`.
- **Failover order.** The Model providers list is reorderable and its order is fallback priority
  (`PUT /api/v1/providers/order`, `coffer provider order`). Each provider has "Use as fallback for
  other providers" (default on). The proxy tries fallbacks in list order and skips providers
  switched off. Every failover is filed in the audit log and shown in Activity.
- **Model tab.** Read-only Fallback ("If X fails: Y" / "No fallback") and the agent's proxy token
  (last four characters, Rotate), from `GET /api/v1/proxy/routes/{agent_uid}` and
  `GET /api/v1/proxy/tokens/{agent_uid}/hint`. Copy says "provider", not "connection".
- **Model providers detail** is one column: Used by, Endpoint (with Route and Fallback), Models
  (with price and source tag per model, Set price…, Reset).
- **Agents pages.** Repair / Repair Coffer's memory hook, the hook-not-approved state (Check again,
  Copy /hooks), the Untrusted hook panel, row menus on the agent's own MCP entries and skills,
  deleting an unmanaged skill, and New file / delete file / the unsaved-changes guard on Config files.

## Impact

- Specs: provider-switching (prices renamed and rewritten; failover order and failover log added).
  The in-flight `revise-web-ui-ia` deltas for provider-switching and agent-registry are updated in
  place for the no-tab detail and the Repair header.
- Code: provider and usage application layers, the model proxy's usage record (`relay_id`), provider
  and proxy routes, the CLI, the web Providers, Model tab, Agents detail tabs, Usage and Activity.
- A bundled data file ships in the daemon build (PyInstaller spec and package data).
