## Why

The Usage page answers two questions. For an agent on an API-key connection it asks how many tokens of each kind the agent used and what they cost, and now that every such request passes through the local model proxy, Coffer can count them exactly. For an agent on a subscription login it asks how much of the five-hour and weekly allowance is left. Only the vendor's server knows that, so Coffer shows the vendor's own number and never an estimate (ADR usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota).

## What Changes

- **Metering.** The proxy writes one record per upstream attempt. It reads tokens in disjoint categories by each wire's rules and marks a cut-off stream as unknown. It spools records to `~/.coffer/proxy-usage/`, and the daemon ingests them with a source and a de-duplication key.
- **Storage.** Migration `0111` adds `usage_requests`, `usage_daily` and `quota_snapshots` to the daemon's database; they will move to `runs.db` when that store lands. Per-request rows follow the MCP invocation window. Daily totals are kept for a year.
- **Cost.** Cost is estimated at ingest from a bundled price snapshot (`2026-09-25`, Anthropic first-party rates), or from a price the connection records for the model. It is stored with the price used. A model with no price is marked unpriced.
- **Reports.** `GET /api/v1/usage/summary|requests|export.csv` and `coffer usage [requests] [--csv]` cover the ranges today, 7d, 30d, this month and custom, grouped by model (with its connection), by agent or by day.
- **Subscription quota.** Codex's comes from `codex app-server` `account/rateLimits/read` and its `updated` notifications. Claude Code's comes from `rate_limit_event` on the sessions Coffer drives. `GET /api/v1/usage/quota`, `POST /api/v1/usage/quota/refresh` and `coffer usage quota [--refresh]` report it "as of" the moment it was seen.
- **Opt-in statusline wrapper.** `coffer usage statusline -- <command>` forwards Claude Code's statusline `rate_limits` and then runs the user's own command. It is documented but never installed.

## Capabilities

### New Capabilities

### Modified Capabilities
- `provider-switching`: usage metering, retention, pricing, reports, subscription quota and the statusline wrapper.

## Impact

- Backend:
  - New: `domain/usage/{pricing,ranges,quota}.py`, `application/usage/`, `infrastructure/usage/spool_reader.py`, `infrastructure/persistence/{usage_models,usage_repo}.py`, migration `0111`, `infrastructure/chat/{codex_rate_limits,quota_observe}.py`, `surfaces/http/usage_*.py`, `surfaces/cli/usage_cmd.py`, `application/provider/usage_lookup.py`.
  - Retention: tables can now follow another table's policy.
  - Chat adapters: they forward quota events.
  - Curated models: they can carry a price.
- Docs: the Usage and quota guide and the CLI/REST references.
