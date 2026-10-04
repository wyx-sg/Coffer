## Why

Provider failover only fires when two connections list the identical model id. Real usage showed zero proxied requests and zero failovers, yet failover was the most complex part of the local model proxy: a route of ordered members, a first-byte hold, cool-downs, per-member key disabling, a spool field and an audit event. The Model providers list order existed only as failover priority.

## What Changes

- Each agent on an API-key or local connection is routed by the local model proxy to exactly that one connection. The proxy relays bytes unchanged, injects the key, meters usage (one usage record per request on metered routes) and returns the upstream's own errors to the agent as sent; when the upstream cannot be reached it answers 502. Agents' own retries handle transient errors.
- Provider config is `{protocol, base_url, secret_ref, models, internal_default, transcribe_default, local_runtime}`.
- The Model providers list is sorted by name, with no order heading, no drag handles and no `PUT /api/v1/providers/order` route; `PATCH /api/v1/providers/{uid}` takes no `fallback`.
- The agent page offers **Rotate proxy token** whenever the agent runs on a provider.
- Audit event types `provider_failover` and `provider_reordered` are gone; usage records carry no `failed_over` field (runs.db migration 0147 drops the column).
- The decision record, the architecture page and the providers guide describe the single-upstream relay.

## Impact

- Spec: `provider-switching` — three requirements removed, four modified (see `specs/`). Its Purpose paragraph, `data-model.md` and `contracts/api.openapi.yaml` follow the code.
- Docs: `docs-site/architecture/model-proxy.md`, `docs-site/guides/providers.md` and their `zh/` pages; the ADR on the local model proxy.
