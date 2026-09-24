## Why

Review of the experimental features found surfaces a switched-off feature still
reached: the kind-agnostic resource routes read, changed and deleted `knowledge`
and `memory` resources (a delete removed a collection's folder), the MCP
handshake and the `coffer-guide` skill still told every agent about
`coffer__write` and `coffer__recall` after those tools had left the list, and
the curation pass kept waiting on a curation owner and on held sync rounds the
user could not reach while `vault_sync` was off.

## What Changes

- experimental-features: a resource whose kind a switched-off feature owns is
  out of reach of `/api/v1/resources` — a route naming its kind or its uid
  answers 404 `FEATURE_DISABLED`, and a list leaves it out. The registry maps
  `knowledge` and `memory` to their kinds; `vault_sync` owns none.
- experimental-features: the handshake instructions and the `coffer-guide`
  skill name only the tools the tool list carries; switching `knowledge` or
  `memory` re-renders the guide.
- knowledge: the handshake requirement says a switched-off feature's tool is
  not named.
- experimental-features: while `vault_sync` is off the vault is treated as a
  single-machine one, so curation waits on neither an owner machine nor a sync
  round.
- The feature service serializes switches through their subscribers, and the
  memory delivery hook reconciles to the state `memory` is in when it runs.
- The CLI tells a daemon older than itself apart from one that has not derived
  this machine's id yet, and the machine picker in the web UI stops waiting
  once the daemon status has failed.

## Capabilities

### New Capabilities

### Modified Capabilities

- `experimental-features`
- `knowledge`

## Impact

- `backend/coffer/domain/features.py`, `surfaces/http/resource_routes.py`,
  `surfaces/http/routing.py`, `surfaces/http/curation_wiring.py`,
  `application/mcp/gateway_instructions.py`,
  `application/knowledge/guide_render.py` and its static body,
  `application/features.py`, `application/memory/delivery_switch.py`, the CLI's
  daemon/channel/curate-owner commands, `frontend/src/lib/hooks/useMachines.ts`.
- The resource-framework contract documents `FEATURE_DISABLED` on
  `/resources`.
