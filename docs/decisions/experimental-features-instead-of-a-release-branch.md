# Experimental Features Instead of a Release Branch

**Status**: Accepted
**Date**: 2026-09-24
**Deciders**: Yuxing Wu (project owner)
**Related**: spec experimental-features, [Distribution](distribution-pyinstaller.md), [The Daemon Binds a Fixed Port](daemon-binds-a-fixed-port.md), [The Desktop Shell Hosts the Shared Frontend](desktop-shell-over-a-shared-frontend.md), [principles](../../docs-site/architecture/principles.md), PR #430

## Context

Every capability lands on `main`, and a release is a tagged `main`. Several of
them — model providers and the proxy, Knowledge, Memory, vault sync — were
redesigned repeatedly and are not proven yet, yet the owner keeps them for good
(the principles' governance rule: shipped capabilities are not removed to
shrink scope). He wants every capability in the one shipped build, so that
anyone can try them, while a person who has not asked for them is not shown
them.

Forces on the answer:

- **One line of development.** A long-lived second branch has already been
  tried here: `feature/workflow` needed a rebase of migration numbers,
  requirement titles and spec files every time `main` moved.
- **The switch has to take effect without a restart.** The web UI offers no
  shutdown control (spec web-ui "Keep daemon shutdown on the command line"), and
  a restart — from Settings → Daemon or the desktop shell's offline banner — is a
  deliberate act, not something flipping a feature should ask of the person.
- **The vault syncs.** Anything stored in the vault reaches every machine
  that syncs it; a feature switched on for testing on one laptop must not switch
  on elsewhere.
- **Builds must behave alike.** A person who tries a feature in the shipped
  build must see what the owner sees in his own; a default that depends on how
  the binary was made would make each build a different product.
- **The API contract is generated.** The OpenAPI document drives the frontend's
  codegen and the contract gates; a switch must not change it.

## Options Considered

### Option A — Runtime feature gates, off by default, switched on per machine (chosen)

`main` keeps every feature, and the shipped build carries all of it. A registry
(`backend/coffer/domain/features.py`) names the experimental ones with the REST
prefixes and resource kinds each owns. It holds four entries: `knowledge`,
`memory`, `sync` and `models` (Model providers, the local model proxy and
Usage). Conversations and Channels, like the shell, Agents, the MCP gateway,
Skills, Secrets, Activity and Settings, are always on and own no entry. Each
feature's state is resolved per read (`backend/coffer/application/features.py`):

1. a pin in `COFFER_FEATURES` (`<key>=on,<other-key>=off`), read once at start;
   a write to a pinned feature answers 409 `FEATURE_PINNED`;
2. the machine's own setting in the `features` object of
   `~/.coffer/daemon-config.json`, the pre-database file the daemon already
   reads for its port;
3. the default: off, for every feature in every build.

Gates act at request time, on every surface:

- **REST**: the feature's routers stay included, behind a dependency that
  answers 404 `FEATURE_DISABLED` naming the key
  (`surfaces/http/feature_dependencies.py`); the kind-agnostic resource routes
  refuse, and lists omit, a kind a switched-off feature owns. Routes stay
  registered, so the OpenAPI schema (`/api/v1/openapi.json`) and the generated
  client never change with a switch.
- **MCP**: each builtin tool records its owning feature
  (`application/builtin_tools.py`). While it is off the tool is absent from
  `tools/list`, and a call to it answers exactly as a call to an unknown tool.
- **Workers**: sync convergence, knowledge curation, memory aggregation and
  distillation read the switch at the top of each round and skip it.
- **CLI**: groups stay registered; a `FEATURE_DISABLED` answer becomes one line
  naming `coffer config set feature.<key> on`.
- **Web**: `/api/v1/daemon/status` carries `features`; a switched-off feature
  looks absent — no sidebar entry, palette hit, Overview tile or page section,
  and its address shows the not-found page — and a switched-on feature's entry
  is labelled Experimental. Settings carries a Features tab, in every build,
  with the four switches; it is the one place that switches them besides
  the CLI.
- **Agent-facing side effects** follow the switch through subscribers: a
  feature that put something in front of agents withdraws it when switched off
  and puts it back when switched on (spec experimental-features "Withdraw what a
  switched-off feature put in front of agents"): `memory` withdraws the memory
  delivery hook and the memory section of `coffer-guide`; `knowledge` withdraws
  the knowledge sections of `coffer-guide` and the channel `/kb`; `models` withdraws the provider projection from agents' own
  configuration and empties the model proxy.

One security detail survives from the earlier channel design and is not a
feature default: a build made from a tag carries a stamp
(`backend/coffer/build_channel.py`, written by `scripts/stamp_channel.py` in the
release workflow before PyInstaller freezes the module) that makes it ignore the
developer-only environment switches for allowed hosts and CORS origins. It
changes nothing a person sees, and experimental features are off by default in
every build.

Pros: one branch and one build; a switch is immediate and per machine; the
contract is stable; a person opts in knowingly. Cons: every gated surface is code
that must be kept complete (a missed surface leaks a feature), a gate costs a
dictionary lookup per request, and an agent that listed tools before a switch
holds a stale list until it lists again. It wins because it is the only option
that serves both the owner and the release from one tree without a restart.

### Option A2 — A release channel decides the default (replaced)

The first form of Option A stamped each build `stable` or `dev` and defaulted
the features off on `stable` and on on `dev`, with the Features tab on `dev`
only. Pros: the owner's own build showed everything with no setup. Cons: two
builds of one product behaved differently, a person on `stable` could not find
the switches in the UI, and "on" depended on how a binary was made rather than on
a choice. It was replaced by a plain off default and a Features tab in every
build.

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

### Option E — Keep the switch in the vault

Store feature state as a vault document next to the other settings. Pros: one
storage mechanism, versioned and audited like other writes, visible to every
machine. Cons: the vault syncs, so switching one machine switches all of them,
and a feature switched on for testing on one laptop would switch on elsewhere.
It loses on that alone; the setting lives in the machine-local
`daemon-config.json`, which never syncs, is read before the daemon binds its
port or opens anything else, and is the file `coffer config` already edits for
other per-machine daemon settings. A file under `local/` would also stay
machine-local; it was not chosen because `daemon-config.json` already exists for
exactly this kind of setting and needs no second place to look.

### Option F — A third-party feature-flag service

LaunchDarkly, Unleash, or a remote JSON of flags. Pros: targeting, gradual
rollout, a dashboard. Cons: a network dependency and an account for a
local-first, single-user tool, and a remote party deciding what a local vault
exposes. It loses; four boolean keys per machine need none of it.

## Decision

**`main` keeps every feature. Features that are not proven are registered as
experimental, and are off by default in every build. Each machine can switch each
one at runtime, from the Features tab of Settings or `coffer config set
feature.<key> on|off`, and the switch applies at request time on every
surface.** The four features (`knowledge`, `memory`, `sync`, `models`) are
independent, and the dependencies between them are soft — no feature fails
because another is off; a surface that would embed its data leaves that section
out (spec experimental-features "Keep dependencies between features soft").
Rules a change must respect:

- State resolves pin → machine setting → off; the machine setting never syncs.
- A gate hides; it never removes. Routes and CLI groups stay registered, kinds
  stay registered, and switching off keeps every resource, file, configured
  remote and history untouched (spec experimental-features "Keep what a
  switched-off feature holds").
- A switched-off feature looks absent in the UI: no notice, no switch-on button
  outside Settings → Features.
- Migrations of `runs.db` always run, whatever the switches say, so switching a
  feature on never needs a schema change.
- A new unfinished capability lands on `main` behind a registry entry, not on a
  side branch. A feature leaves the registry once it is proven: its entry and
  every gate that names it are deleted, and a migration strips its stored switch
  from `daemon-config.json`.
- A feature never hard-depends on another; a cross-feature link degrades.

## Consequences

- A person who installs a release sees only the always-on capabilities until they
  switch a feature on; the owner's own build behaves the same.
- Experimental is not removal. A gated feature stays part of the product; the
  gate only decides what is shown until someone opts in. When a feature is
  proven, its registry entry and every gate that names it are deleted.
- Every surface a gated feature touches carries a gate, and a surface added
  later must add one; the spec's "Close every surface of a switched-off feature"
  and "Make a switched-off feature look absent in the UI" are the checklist.
