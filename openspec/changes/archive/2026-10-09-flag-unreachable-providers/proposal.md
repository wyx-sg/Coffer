## Why

A model provider whose endpoint does not answer, or refuses its key, showed
no error anywhere until the person opened it: the health probe ran only for
the open provider, and only in the browser. The provider list marked only the
open row, and Overview's "Needs you" had no provider source at all, so an
agent could be failing every turn on a revoked key while Coffer said nothing.

## What Changes

- The daemon keeps a health verdict per connection — Reachable, Key rejected
  or Unreachable — in `derived.db`. It is written by a model-list check (no
  token spent) at boot and every 30 minutes for every enabled connection,
  again right after a connection is edited, by the detail page's own probe,
  and by the agents' real requests through the local model proxy (a 401/403
  or a connection that never opened, read from the usage records).
- New routes: `GET /api/v1/providers/health` (every kept verdict, no network)
  and `POST /api/v1/providers/{uid}/check` (check one now).
  `POST /api/v1/models/list-models` takes an optional `connection_uid`.
- The provider list marks every failing row in red with its status, not only
  the open one.
- Overview "Needs you" lists a connection something runs on (an agent, or
  Coffer's speech to text) whose endpoint is unreachable
  (`provider_unreachable`, Check again in place) or refuses its key
  (`provider_key_rejected`, Replace key on its page).

## Capabilities

### New Capabilities

### Modified Capabilities
- `provider-switching`: adds "Know each connection's health without opening it".
- `resource-framework`: "Report what needs a person across every kind" lists the provider signals.

## Impact

Backend: `domain/provider/health.py`, `application/provider/health.py` and
`attention.py`, `infrastructure/provider/health_repo.py`, a `provider_health`
table in `derived.db`, the usage ingest's `observe` hook, the new routes and
their wiring. Frontend: the provider list rows, the detail probe, Overview's
in-place Test. Docs: the Model providers and Overview guides (en, zh). Canvas:
the Agents canvas provider list, the Shell canvas Overview list.
