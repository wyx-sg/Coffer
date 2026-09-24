## Why

`main` carries every capability, including three whose design is still moving:
vault sync, the knowledge layer and the memory layer have each been redesigned
several times in the last month. A release built from `main` hands all of them
to every user. The owner wants one line of development — everything lands on
`main` and is exercised there — and a release that exposes only what is ready,
without a second long-lived branch to keep in step.

## What Changes

- Every build carries a **release channel**: `stable` for a tagged release,
  `dev` for everything else. The daemon's status reports it.
- One registry declares the **experimental features**: `vault_sync`,
  `knowledge` and `memory`. On `stable` they start off; on `dev` they start on.
- Each machine can switch a feature on or off from Settings → General, from
  `coffer daemon features`, or over REST. The choice is kept in
  `~/.coffer/daemon-config.json` and takes effect at once, without a restart.
  `COFFER_FEATURES` pins a feature for tests and CI.
- A feature that is off closes every surface it has: its REST routes answer
  404 `FEATURE_DISABLED`, its MCP tools leave the tool list, its CLI group says
  how to switch it on, its sidebar entry and pages disappear, its tray item and
  desktop attention stop, and its background passes skip their rounds.
- Switching a feature off keeps everything it holds. Switching it back on
  resumes where it stopped.
- The knowledge feature off also answers a channel `/save` with a notice and
  drops the knowledge catalogue from the delivered `coffer-guide` skill. The
  memory feature off also takes the memory delivery hook out of every agent,
  and switching it on puts the hook back.

## Capabilities

### New Capabilities

- `experimental-features`: the release channel, the feature registry, how a
  feature's state is decided and changed, and what a switched-off feature
  closes.

### Modified Capabilities

- `daemon`: the status probe reports the release channel, the feature states
  and this machine's id and name.
- `web-ui`: the sidebar lists the entries of switched-on features only; the
  General tab of Settings carries the experimental-features card.

## Impact

Backend: a feature service and its REST routes, the daemon status schema, a
request gate on the three features' route prefixes, the builtin-tool list, the
CLI root, the sync, curation, aggregation and distil workers, the memory
delivery reconcile, the channel `/save` command and the `coffer-guide` catalogue.
Frontend: the sidebar, the router, Settings → General, a regenerated client.
Desktop: the tray's Sync item and the sync watcher. Packaging: the release
workflow stamps `stable`. Contracts: daemon. A new ADR records the choice of
feature gates over a separate release branch.
