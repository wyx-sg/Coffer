## 1. Registry and state

- [x] 1.1 Empty the registry: `EXPERIMENTAL_FEATURES = ()` in `backend/coffer/domain/features.py`; delete the `vault_sync`, `knowledge` and `memory` entries and the constants naming them
- [x] 1.2 `FeatureService` ignores a stored setting for a key the registry does not name — logged, never listed; `/daemon/features` lists nothing, `/daemon/status` reports `features: {}`, `coffer config list feature.` prints nothing and exits 0
- [x] 1.3 Migration `0116` strips `vault_sync`, `knowledge` and `memory` from the `features` object of `~/.coffer/daemon-config.json`, keeping every other key and leaving a missing or unreadable file alone

## 2. Gates on the three keys

- [x] 2.1 Routes: the `/api/v1/sync`, `/api/v1/knowledge` and `/api/v1/memory` prefixes and the `knowledge` and `memory` kinds are always open
- [x] 2.2 MCP: `coffer__write` is always advertised; the handshake instructions always name it and the memory root
- [x] 2.3 Guide: the `coffer-guide` skill's `<!-- when: -->` spans are removed, so it always documents `coffer__write`, the knowledge catalogue and the memory root
- [x] 2.4 Memory: the root directory gate and the delivery-hook switch subscriber are deleted; the connection part's `enabled()` is gone, so `memory_hook` is a part of every agent type with a hook adapter; a missing hook in a connected agent is installed only by connecting it or applying the reconcile item
- [x] 2.5 Channels: `/kb` is always handled and always in `/help` and every registered menu; the knowledge-conditional roster flag, menu and help branches are deleted
- [x] 2.6 Workers: the curation, distil, aggregate and converge workers lose their feature switches; the curation "sync off → single machine" branch is deleted
- [x] 2.7 CLI: `coffer path knowledge` and `coffer path memory` lose their feature refusal
- [x] 2.8 Attention: the sync attention source loses its `vault_sync` tag

## 3. Frontend and desktop

- [x] 3.1 Sidebar: Knowledge, Memory and Sync lose their feature tags, so they carry no "Experimental" marker and are never left out
- [x] 3.2 Settings › General: the Experimental features card stays mounted and renders nothing — no card, no heading — while the registry is empty
- [x] 3.3 Desktop shell: delete `sync_gate`, so the menu bar dot, the "needs you" entry and the Dock badge follow sync's attention alone

## 4. Tests

- [x] 4.1 `acceptance(experimental-features, …)` for "an empty registry lists no features", "a stored setting for a feature the registry does not name is ignored", "graduating a feature strips its stored setting" (`test_migration_0116.py`), "switching a feature off and on keeps what it holds", "a switched-off feature's attention source is not asked" and "the general tab shows nothing while no feature is registered"
- [x] 4.2 The generic experimental-features scenarios kept by name ("a switched-off feature's routes answer feature disabled", "… resources are out of reach of the resource routes", "… tool leaves the tool list", "… command says how to switch it on", "… page says it is switched off", "switching a feature on opens its surfaces without a restart", "unsetting a feature returns it to the channel default", "a stable build starts with every experimental feature off", "a machine setting overrides the channel default", "a pinned feature cannot be switched", "agents are told only about the tools they have", "the general tab switches a feature", "a switched-on feature's entry says it is experimental") run against a registry patched with a fake feature
- [x] 4.3 Delete the markers of the removed scenarios: experimental-features "the registry names the three features", "a switched-off feature's pass skips its round", "curation does not wait on sync while vault sync is off", "switching knowledge off and on keeps the collections", "switching memory off removes the delivery hook", "switching knowledge off drops the catalogue from the guide", "a channel save while knowledge is off saves nothing"; agent-registry "connect leaves out a part whose feature is off"; channels "/kb is offered only while knowledge is on"; channels/telegram "/kb leaves the menu while knowledge is off"
- [x] 4.4 Update the tests behind the rewritten bodies: mcp-gateway "the gateway advertises exactly two built-in tools", daemon "daemon status names this machine and its features", resource-framework "a switched-off feature's signals are left out", web-ui "a switched-off feature leaves the sidebar", memory "the agent's command-line view reports delivery state" and "no memory tool is listed, and delivery names the memory root", knowledge "the manual names two tools, the memory root and the log reader"

## 5. Docs

- [x] 5.1 `docs-site/guides/experimental-features.md`: no feature is registered today; how a feature joins and leaves; Sync, Knowledge and Memory are always on
- [x] 5.2 The docs-site pages that name the three switches (`guides/daemon.md`, `guides/web-ui.md`, `guides/troubleshooting.md`, `start/install.md`, `start/concepts.md`, `reference/configuration.md`, `reference/error-codes.md`, `reference/mcp-tools.md`, `reference/filesystem.md`, `architecture/*`) follow
- [x] 5.3 ADR [Experimental Features Instead of a Release Branch](../../../docs/decisions/experimental-features-instead-of-a-release-branch.md): record the graduation of the three and that the mechanism stays with an empty registry

## 6. Close

- [x] 6.1 `make verify`, `openspec validate --all --strict`, `python3 scripts/check_spec_citations.py` and `python3 scripts/audit_acceptance.py` pass
- [x] 6.2 Archive the change in the same PR (`npx openspec archive graduate-experimental-features --yes`)
