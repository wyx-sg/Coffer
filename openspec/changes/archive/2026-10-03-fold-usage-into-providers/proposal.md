## Why

Usage was a page of its own with two halves: what Coffer's proxy metered for
API-key requests, and the subscription quota each agent reported for its own
login. The quota half is the vendor's number relayed through the sessions
Coffer drives (and a short-lived `codex app-server`), it covered only part of a
person's use, and it needed a status-line wrapper edited into Claude Code's
settings to be complete. The finished design drops it. What is left — cost and
tokens of requests through Coffer — belongs next to the providers those
requests went through, so Usage becomes a tab of Model providers and the page
and its sidebar entry go.

## What Changes

- web-ui: the sidebar has fourteen entries — "Keep the sidebar to its fifteen
  entries" is renamed "Keep the sidebar to its fourteen entries" and System
  holds Secrets, Activity and Sync; `/usage` is no longer a route. The palette,
  Settings and Overview requirements follow (Overview's Usage tile opens the
  Usage tab).
- provider-switching: new "Show metered usage on a Usage tab of Model
  providers" — Providers | Usage under one header, the shared date-only time
  range, Agent and Provider pills, Export CSV on the filter row, five tiles
  without a frame, a data-colour chart, a segmented By model / agent / day over
  a bordered table, and a whole-page first run.
- provider-switching: **removed** "Show a subscription's official quota as of
  when it was seen" and "Offer an opt-in statusline wrapper"; the price and
  connection requirements stop naming quota.
- experimental-features: `models` skips only the usage ingest and the price
  refresh; the sidebar entry list names Model providers alone.

## Impact

- Removed: `GET /api/v1/usage/quota`, `POST /api/v1/usage/quota/refresh`,
  `POST /api/v1/usage/quota/statusline`, `coffer usage quota`,
  `coffer usage statusline`, `COFFER_QUOTA_POLL`, the Codex rate-limit reader,
  the chat kind's quota observer, and the `quota_snapshots` table (migration
  0140 drops it).
- A `statusLine` command a person pointed at `coffer usage statusline` in an
  agent's settings stops working until they set it back.
- The frontend loses `/usage`, `UsagePage`, the quota components and the old
  range control; Model providers gains `?tab=usage`.
