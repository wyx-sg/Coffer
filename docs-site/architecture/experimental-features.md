# Release Channel & Experimental Features

::: tip Mental model
`main` carries every capability; a feature that is not ready ships **switched off** instead of living on a second branch (ADR experimental-features-instead-of-a-release-branch, spec `experimental-features`). A build carries a release channel, the channel decides each feature's default, and each machine can override that default for itself. The switch decides who sees a feature by default, not whether it exists. For the user-facing view — which features, how to switch them — see the guide page [Experimental features](/guide/experimental-features).
:::

## Channel

`coffer/build_channel.py` holds `CHANNEL = "dev"` in the repository. The release workflow runs `scripts/stamp_channel.py stable` before PyInstaller, so only a tagged release is `stable`; a source run, `make desktop` and the owner's own frozen build are all `dev`. The frontend and the desktop shell stamp nothing — they read `channel` from `GET /api/v1/daemon/status`. See [Distribution → Release pipeline](/architecture/distribution#release-pipeline).

## Registry

`domain/features.py` declares the experimental features — `vault_sync`, `knowledge`, `memory` — and, per key, the REST prefixes and resource kinds it owns, so no gate spells a prefix or a kind of its own (`surfaces/http/routing.py` gates a router by its prefix). A capability outside the registry is always on.

## State

`application/features.py`'s `FeatureService` resolves each key per read, in this order:

1. a `COFFER_FEATURES` pin (`vault_sync=on,memory=off`), read once at start; a write to a pinned key answers 409 `FEATURE_PINNED`;
2. the machine's own setting, in the `features` object of `~/.coffer/daemon-config.json` (`infrastructure/daemon/feature_settings.py`);
3. the channel default — off on `stable`, on on `dev`.

The setting is machine-local on purpose: the database syncs, and a switch kept there would switch every machine at once. `set` writes the file before it changes the held value and then notifies subscribers, one switch at a time.

## Gates run at request time

Gates run at request time, not at wiring time, so a switch takes effect without a restart:

- **REST.** Routes stay registered (the OpenAPI document and the generated client never change with a switch); `surfaces/http/feature_dependencies.py` gives each gated router a dependency that answers 404 `FEATURE_DISABLED` naming the key, and the kind-agnostic `/api/v1/resources` routes refuse a switched-off feature's kinds the same way and leave them out of a list.
- **MCP.** Builtin tools of a switched-off feature leave `tools/list` and answer a call as an unknown tool, and neither the handshake instructions nor the `coffer-guide` skill name them.
- **Workers.** With `vault_sync` off, curation treats the vault as single-machine; the upkeep workers skip their round.
- **CLI.** The shared error path turns `FEATURE_DISABLED` into one line naming `coffer daemon features enable <key>`.
- **Web UI and tray.** Both filter on the `features` list the daemon status carries.

## Switching surfaces

`GET /api/v1/daemon/features`, `PUT /api/v1/daemon/features/{key}` (`surfaces/http/feature_routes.py`), `coffer daemon features list|enable|disable` (`surfaces/cli/daemon_features_cmd.py`), and the Experimental features card under Settings → General.

## Off keeps data

Kinds stay registered and migrations always run; a switched-off feature's resources, files, remote configuration and history are untouched, and switching it back on resumes where it stopped. A feature leaves the registry once it is ready, and its gates are deleted with it.
