## Why

Sync, Knowledge and Memory were put behind experimental switches so a stable build could ship
without them while they settled. They are ready, and the switches now cost more than they
protect. Each one is a gate on a route family, a tool,
a hook, a guide section, a channel command, worker passes and a sidebar label, and every gate is
a branch that must be kept right in both positions. A stable user who never finds the switch
never meets three of Coffer's main capabilities.

The mechanism itself stays useful: the next feature that is not ready yet should be able to
join it with one registry entry, and leave it the same way.

## What Changes

- **Sync (`vault_sync`), Knowledge (`knowledge`) and Memory (`memory`) graduate and are always
  on.** Their registry entries are deleted, so the registry (`EXPERIMENTAL_FEATURES`) is empty,
  and so is every gate that named them:
  - the route prefixes `/api/v1/sync`, `/api/v1/knowledge` and `/api/v1/memory` and the `knowledge`
    and `memory` kinds on the resource routes are always open;
  - `coffer__write` is always advertised, and the handshake instructions and the `coffer-guide`
    skill always document `coffer__write`, the knowledge catalogue and the memory root (the
    guide's `<!-- when: -->` spans are removed);
  - `coffer path knowledge` and `coffer path memory` always answer;
  - the memory delivery hook is part of every connection of an agent type with a hook adapter.
    Nothing installs it on a feature switch any more: a missing hook in a connected agent is
    reported by a boot or periodic reconcile pass and installed only when the user connects the
    agent (`coffer agent connect`) or applies that item;
  - the channel `/kb` command is always in `/help` and in every registered menu;
  - the curation, distil, aggregate and converge workers run on their own switches only, and
    curation no longer treats the vault as single-machine because sync was off;
  - the sync attention source is untagged, so sync items and the desktop shell's sync marks
    always show.
- **The Knowledge, Memory and Sync sidebar entries lose their "Experimental" marker.**
- **Migration 0121** strips `vault_sync`, `knowledge` and `memory` from the `features` object of
  `~/.coffer/daemon-config.json`, keeping every other key and leaving a missing or unreadable file
  alone. A stored setting for a key the registry does not name is ignored by every read — logged,
  never listed.
- **The mechanism stays for future features**: the registry, the channel defaults (off on
  `stable`, on on `dev`), `COFFER_FEATURES` pins, `GET/PUT/DELETE /api/v1/daemon/features[/{key}]`,
  `coffer config set|unset|list feature.<key>`, the `FEATURE_DISABLED` / `FEATURE_PINNED` /
  `FEATURE_UNKNOWN` errors, the generic gates, the page notice and the generic sidebar marker.
  Settings › General's Experimental features card renders only while the registry names a
  feature. With the registry empty, `/daemon/features` lists nothing, `/daemon/status` reports
  `features: {}`, and `coffer config list feature.` prints nothing and exits 0.

## Capabilities

### New Capabilities

### Modified Capabilities
- `experimental-features`: the registry is empty and says how a feature joins and leaves; every
  requirement is stated for a generic registered feature; an unregistered stored setting is
  ignored and a graduation migration strips it; the General card renders only while a feature
  is registered.
- `agent-registry`: the memory hook is a connection part for every agent type with a hook
  adapter; disconnect removes every part the type has.
- `daemon`: the status probe's `features` map names every registered feature and is empty when
  none is.
- `knowledge`: the guide and the handshake always carry `coffer__write` and the memory root.
- `mcp-gateway`: `coffer__write` is always advertised.
- `memory`: the delivery hook is installed by connecting the agent or applying the reconcile item,
  never by a feature switch or an unattended pass.
- `resource-framework`: the attention scenario for a switched-off feature is generic.
- `web-ui`: Knowledge, Memory and Sync are ordinary sidebar entries; the General tab lists
  experimental features only while one is registered.
- `channels`, `channels/telegram`: `/kb` is always offered in help and in every menu.

## Impact

- Backend: `domain/features.py` (empty registry), `application/features.py` (unregistered keys
  ignored), the route, kind, tool, path, hook, guide, channel, worker, curation and attention gates
  on the three keys, and migration `0121`.
- Frontend: the sidebar's feature tags on Knowledge, Memory and Sync, the Experimental features
  card rendered only while the registry is non-empty, and the tests that switched the three.
- Desktop: the shell's `sync_gate` on the sync attention marks.
- Tests: acceptance markers for the new and renamed scenarios, with the removed ones' markers
  deleted.
- Docs: `docs-site/guides/experimental-features.md` and the pages that named the three switches,
  the ADR
  [Experimental Features Instead of a Release Branch](../../../docs/decisions/experimental-features-instead-of-a-release-branch.md).
