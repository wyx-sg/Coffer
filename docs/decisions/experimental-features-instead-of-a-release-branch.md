# Experimental Features Instead of a Release Branch

**Status**: Accepted
**Date**: 2026-09-24
**Deciders**: Yuxing Wu (project owner)
**Related**: spec experimental-features, [Distribution](distribution-pyinstaller.md), [The Daemon Binds a Fixed Port](daemon-binds-a-fixed-port.md), [The Desktop Shell Hosts the Shared Frontend](desktop-shell-over-a-shared-frontend.md), [principles](../../docs-site/architecture/principles.md), PR #430

## Context

Every capability lands on `main`, and a release is a tagged `main`. Three of
them — vault sync, the knowledge layer and the memory layer — were redesigned
several times in one month and are not ready for anyone but the owner, yet the
owner keeps them for good (the principles' governance rule: shipped capabilities
are not removed to shrink scope). He wants to keep testing everything, in the
installed app, while a release hands users only what is ready.

Forces on the answer:

- **One line of development.** A long-lived second branch has already been
  tried here: `feature/workflow` needed a rebase of migration numbers,
  requirement titles and spec files every time `main` moved.
- **The switch has to take effect without a restart.** The web UI offers no
  daemon restart or shutdown control (spec web-ui "Leave daemon controls to the
  CLI"). The desktop shell's offline banner has a Restart, but only when the
  daemon is already unreachable, and the browser host has none at all.
- **The database syncs.** Anything stored in `coffer.db` reaches every machine
  of the vault; a feature switched on for testing on one laptop must not switch
  on elsewhere.
- **The frozen build is not a release.** The owner's own testing build is a
  PyInstaller binary too, so "is this frozen" cannot mean "is this a release".
- **The API contract is generated.** The OpenAPI document drives the frontend's
  codegen and the contract gates; a switch must not change it.

## Options Considered

### Option A — Runtime feature gates keyed on a stamped release channel (chosen)

`main` keeps every feature. A registry (`backend/coffer/domain/features.py`)
names the experimental ones — `vault_sync`, `knowledge`, `memory` — with the
REST prefixes and resource kinds each owns. A build carries a channel,
`CHANNEL` in `backend/coffer/build_channel.py`: `dev` in the repository, and
rewritten to `stable` by `scripts/stamp_channel.py` in the release workflow on a
tag, before PyInstaller freezes the module. Each feature's state is resolved per
read (`backend/coffer/application/features.py`):

1. a pin in `COFFER_FEATURES` (`vault_sync=on,memory=off`), read once at start;
   a write to a pinned feature answers 409 `FEATURE_PINNED`;
2. the machine's own setting in the `features` object of
   `~/.coffer/daemon-config.json`, the pre-database file the daemon already
   reads for its port;
3. the channel default: off on `stable`, on on `dev`.

Gates act at request time, on every surface:

- **REST**: the feature's routers stay included, behind a dependency that
  answers 404 `FEATURE_DISABLED` naming the key
  (`surfaces/http/feature_dependencies.py`); the kind-agnostic resource routes
  refuse, and lists omit, a kind a switched-off feature owns. Routes stay
  registered, so `/openapi.json` and the generated client never change with a
  switch.
- **MCP**: each builtin tool records its owning feature
  (`application/builtin_tools.py`). While it is off the tool is absent from
  `tools/list`, and a call to it answers exactly as a call to an unknown tool.
- **Workers**: sync convergence, knowledge curation, memory aggregation and
  distillation read the switch at the top of each round and skip it.
- **CLI**: groups stay registered; a `FEATURE_DISABLED` answer becomes one line
  naming `coffer daemon features enable <key>`.
- **Web and desktop**: `/api/v1/daemon/status` carries `features`; the sidebar
  filters on it, a gated page links to Settings → General, and the desktop tray
  drops its Sync entry (`desktop/src/sync_gate.rs`).
- **Agent-facing side effects** follow the switch through subscribers: `memory`
  off removes the memory delivery hook from every agent and on reinstalls it;
  `knowledge` off rewrites `coffer-guide` without its catalogue and makes a
  channel `/save` answer that knowledge is off (spec experimental-features
  "Withdraw what a switched-off feature put in front of agents").

Pros: one branch; the owner's installed `dev` build has everything and a tagged
build hides the unready; a switch is immediate and per machine; the contract is
stable. Cons: every gated surface is code that must be kept complete (a missed
surface leaks a feature), a gate costs a dictionary lookup per request, and an
agent that listed tools before a switch holds a stale list until it lists again.
It wins because it is the only option that serves both the owner and the
release from one tree without a restart.

### Option B — A `stable` release branch that receives only finished features

Pros: a release contains nothing unfinished, by construction. Cons: a feature
merged into `main` can only leave the release by revert or cherry-pick, and the
branch drifts — migration numbers, requirement titles and spec files collide on
every rebase, the cost `feature/workflow` already showed. Git flow
(`develop` plus `main`) is the same option with the same flaw: `develop` merges
into `main` whole, so it cannot choose which features ship. It loses on
maintenance cost.

### Option C — Exclude the code at build time

Leave the experimental packages out of the frozen release (PyInstaller excludes,
conditional router tables). Pros: the release carries no dormant code at all.
Cons: a release user can never switch a feature on to try it; the OpenAPI
document and the generated client would differ between builds; and the release
would run a code shape nobody tests day to day. It loses on testability.

### Option D — Gate at wiring time, applied by a restart

Read the switches once at start and simply not wire a disabled feature's
routers, tools and workers. Pros: simpler — no per-request check, a disabled
feature has no presence at all. Cons: a switch from the web UI could not take
effect, because the UI has no restart control, and the browser host cannot
restart a daemon at all. It loses on that; the upkeep workers already read their
own switches every round, so request-time gating extends an existing pattern.

### Option E — Keep the switch in the database

Store feature state in `coffer.db` next to the other settings. Pros: one storage
mechanism, audited like other writes. Cons: the database syncs, so switching one
machine switches all of them. It loses on that alone; the setting lives in the
machine-local `daemon-config.json`, which never syncs.

### Option F — A third-party feature-flag service

LaunchDarkly, Unleash, or a remote JSON of flags. Pros: targeting, gradual
rollout, a dashboard. Cons: a network dependency and an account for a
local-first, single-user tool, and a remote party deciding what a local vault
exposes. It loses; three boolean keys per machine need none of it.

## Decision

**`main` keeps every feature. Features that are not ready are registered as
experimental, and are off by default on a `stable` build and on by default on
every other build. Each machine can switch each one at runtime, from Settings →
General or `coffer daemon features`, and the switch applies at request time on
every surface.** Rules a change must respect:

- The channel is a constant stamped before the freeze, never inferred from
  `sys.frozen`.
- State resolves pin → machine setting → channel default; the machine setting
  never syncs.
- A gate hides; it never removes. Routes and CLI groups stay registered, kinds
  stay registered, and switching off keeps every resource, file, configured
  remote and history untouched (spec experimental-features "Keep what a
  switched-off feature holds").
- Migrations always run, whatever the switches say, so switching a feature on
  never needs a schema change.
- A new unfinished capability lands on `main` behind a registry entry, not on a
  side branch. A feature leaves the registry once it is ready, and its gates are
  deleted with it.

## Consequences

- A tagged release shows only stable features; the owner's own frozen build is
  `dev` and shows everything.
- Experimental is not removal. The three features stay part of the product; the
  gate only decides who sees them by default.
- Every surface a gated feature touches carries a gate, and a surface added
  later must add one; the spec's "Close every surface of a switched-off feature"
  is the checklist.
- Sync's machinery is still constructed while `vault_sync` is off, because
  curation takes its lock; only its rounds are skipped.
