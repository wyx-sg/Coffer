## 1. Backend

- [x] 1.1 Route each agent to its one connection in the proxy; drop the fallback members, first-byte hold, cool-down and key disabling
- [x] 1.2 Remove `fallback` and `position` from the provider schema; remove `PUT /api/v1/providers/order`
- [x] 1.3 Remove `provider_failover` and `provider_reordered`; drop `failed_over` from usage records (runs.db migration 0147)
- [x] 1.4 Regenerate the wire contract

## 2. Frontend

- [x] 2.1 Sort the Model providers list by name; remove the order heading, drag handles and the fallback switch; offer Rotate proxy token whenever the agent runs on a provider
- [x] 2.2 Remove failover sentences from the Activity page

## 3. Docs

- [x] 3.1 Rewrite the local-model-proxy ADR, `model-proxy.md` and `providers.md` (en and zh)
- [x] 3.2 Update `provider-switching` Purpose and `data-model.md`
