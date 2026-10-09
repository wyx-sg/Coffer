## Why

Vault sync and model providers have been in daily use since they shipped as
experimental features. Keeping them behind a switch that is off by default
hides two working parts of the product from every new machine, and every page
and surface still carries the gates and the **Experimental** label. They are
ready to be regular features.

## What Changes

- `sync` and `models` leave the experimental-feature registry and enter the
  table of graduated features (spec experimental-features "Move a graduated
  feature's configuration and clean up a retired one's"). Neither moves a
  setting; at startup the daemon removes their switches from the `features`
  object of `~/.coffer/daemon-config.json`.
- Vault sync is always on: the sync routes are always open and the
  convergence worker always runs its rounds when a remote is configured.
- Model providers are always on: the provider, model, proxy and usage routes
  are always open, the provider projection into agents' own configs always
  runs, the local model proxy always serves, usage ingest and the price-list
  refresh always run, and the `provider` kind is never hidden from the
  resource routes.
- The registry names two features, `knowledge` and `memory`; the features
  listing, the daemon status `features` map and Settings → Features name only
  those two. A `COFFER_FEATURES` pin or a stored setting naming `sync` or
  `models` is an unknown key: logged and ignored.
- Web UI: the Sync and Model providers sidebar entries, pages, Overview tiles,
  first-run cards, palette entries and agent Model section are always shown
  and carry no **Experimental** label.
- zh/en docs and the UI design canvases follow.

Upgrading a machine where either feature was off switches it on. Nothing is
lost or rewritten: a machine with no remote and no provider connection sees
empty pages; a machine that holds a provider connection choice has it
projected into the agent again, exactly as switching `models` on did before.

## Capabilities

### Modified Capabilities

- `experimental-features`: two features instead of four; the sync and models
  closing requirements are removed.
- `vault-sync`, `provider-switching`, `agent-registry`, `daemon`, `web-ui`,
  `secret`: drop the clauses that describe sync or models switched off.

## Impact

- Backend: `domain/features.py`, the sync and provider wiring, the usage
  wiring, the sync attention source, their tests.
- Frontend: `lib/features.ts`, navigation, Overview, agent model surfaces,
  Settings → Features, their tests.
- Docs: the experimental-features guide and every page that says sync or
  model providers must be switched on first (zh and en).
- Design canvases: Settings → Features and the sidebar.
