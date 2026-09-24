# Experimental Features Instead of a Release Branch

**Status**: Accepted
**Date**: 2026-09-24
**Deciders**: Yuxing Wu (project owner)
**Related**: spec [experimental-features](../../openspec/specs/experimental-features/spec.md); [Product Scope Is Settled](product-scope-is-settled.md)

## Context

Every capability lands on `main`, and a release is a tagged `main`. Three of
them — vault sync, the knowledge layer and the memory layer — have been
redesigned several times in a month and are not ready for anyone but the owner.
The owner wants to keep testing everything while releasing only what is ready.

## Decision

**`main` keeps every feature. Features that are not ready are declared
experimental and switched off by default in a `stable` build.** The release
workflow stamps `stable`; every other build is `dev` and has every feature on.
Each machine can switch a feature on or off at runtime. The setting lives in
`~/.coffer/daemon-config.json` and never syncs. A feature leaves the registry
once it is ready, and its gates are then deleted.

## Alternatives Considered

- **A `stable` branch that receives only finished features.** Rejected. A
  feature merged into `main` cannot be taken out without a revert or a
  cherry-pick, and a long-lived second branch drifts: migration numbers,
  requirement titles and spec files collide on every rebase. The
  `feature/workflow` branch has already shown that cost.
- **Git flow (`develop` plus `main`).** Rejected for the same reason:
  `develop` merges into `main` whole, so it cannot choose which features ship.
- **Gate at wiring time, with a restart to apply.** Rejected. The web UI has no
  restart control (spec web-ui "Leave daemon controls to the CLI"), so a
  switch made there could not take effect. The upkeep workers already read
  their switches on every round.
- **Keep the switch in the database.** Rejected. The database syncs, so
  switching one machine would switch all of them.

## Consequences

- Experimental is not removal: [Product Scope Is Settled](product-scope-is-settled.md)
  still holds for sync, knowledge and memory. The gate only decides who sees
  them by default.
- New unfinished work lands on `main` behind a registry entry instead of on a
  side branch.
- Migrations always run, whatever the switches say, so switching a feature on
  never needs a schema change.
