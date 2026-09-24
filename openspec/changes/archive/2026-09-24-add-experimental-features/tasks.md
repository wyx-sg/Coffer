## 1. Backend core

- [x] 1.1 `coffer/build_channel.py` (`CHANNEL = "dev"`) and `scripts/stamp_channel.py`; `release.yml` stamps `stable` before building binaries
- [x] 1.2 Domain registry of experimental features (`vault_sync`, `knowledge`, `memory`) and the surfaces each owns
- [x] 1.3 `features` read/write in `infrastructure/daemon/config.py`; `COFFER_FEATURES` parsing
- [x] 1.4 `FeatureService`: resolve pin → setting → channel default, `is_enabled`, `set`, change subscribers
- [x] 1.5 `GET /api/v1/daemon/features`, `PUT /api/v1/daemon/features/{key}`; `channel` and `features` on `/daemon/status`
- [x] 1.6 `coffer daemon features list|enable|disable`; `coffer daemon status` prints the channel; the CLI error path maps `FEATURE_DISABLED`

## 2. Gates

- [x] 2.1 REST: a `require_feature` dependency on the sync, knowledge and memory routers (404 `FEATURE_DISABLED`)
- [x] 2.2 MCP: builtin tools carry their owning feature; list omits and call answers unknown when off
- [x] 2.3 Workers: converge, curation, aggregation and distil skip rounds while their feature is off
- [x] 2.4 Memory delivery reconcile follows the `memory` switch
- [x] 2.5 `coffer-guide` catalogue follows the `knowledge` switch; channel `/save` answers while off
- [x] 2.6 Web: `features` from status; sidebar filter; gated routes render a notice linking to Settings → General
- [x] 2.7 Web: Experimental features card on Settings → General, en/zh strings
- [x] 2.8 Desktop: no Sync tray item and no sync polling while `vault_sync` is off

## 3. Tests

- [x] 3.1 Acceptance-marked tests for every new scenario in `experimental-features`
- [x] 3.2 Acceptance-marked tests for the modified `web-ui` scenarios

## 4. Docs and contracts

- [x] 4.1 `openspec/specs/daemon/contracts/api.openapi.yaml` (or the owning contract) for the new routes and status fields; regenerate the frontend client
- [x] 4.2 ADR "Experimental Features Instead of a Release Branch"; link it from Product Scope Is Settled
- [x] 4.3 `docs/architecture.md` and `docs-site` guide: channels, features, how to switch
- [x] 4.4 `CONTRIBUTING.md`: new work that is not ready lands behind a feature

## 5. Close

- [ ] 5.1 Run `make verify`
- [ ] 5.2 Archive the change
