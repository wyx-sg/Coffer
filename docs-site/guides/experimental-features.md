---
title: Experimental features
description: Which Coffer features are experimental, what each one gates, and how to switch them on or off per machine from the CLI, the REST API or COFFER_FEATURES.
---

# Experimental features

Some Coffer features are still being designed. They ship in every build but are switched off by default in a release build, and each machine decides for itself whether to turn them on. This page lists the experimental features, what each one controls, and how to switch them.

## Release channels

Every Coffer build carries a release channel:

| Channel | Which builds | Experimental features by default |
| --- | --- | --- |
| `stable` | Builds the release workflow makes from a tag: the desktop app and the release archive | Off |
| `dev` | Every other build, including a source install and a local desktop build | On |

See which channel you are on:

```sh
coffer daemon status
```

```text
status:  ready
version: 0.2.0
channel: stable
port:    8000
pid:     41822
```

`coffer config list feature.` names the channel too.

## The features

| Key | Name in the UI | What it gates |
| --- | --- | --- |
| `vault_sync` | Sync | Converging this vault with a git remote you own: the **Sync** page, `coffer sync`, the `/api/v1/sync` routes and the background converge rounds. See [Vault sync](/guides/vault-sync). |
| `knowledge` | Knowledge | Knowledge collections under `~/.coffer/knowledge/`: the **Knowledge** page, `coffer knowledge`, the `/api/v1/knowledge` routes, the `coffer__write` tool, the knowledge catalogue in the `coffer-guide` skill, the curation pass, and saving to knowledge from a chat channel. See [Knowledge](/guides/knowledge). |
| `memory` | Memory | Memory aggregated from your agents' own stores: the **Memory** page, `coffer memory`, the `/api/v1/memory` routes, the aggregation and distil passes, and the session-start hook that delivers memory into agents. See [Memory](/guides/memory). |

Everything else in Coffer is always on.

## Switch a feature on or off

A switch takes effect at once, with no restart, and is kept in `~/.coffer/daemon-config.json` on this machine only. It is never synced, so switching a feature on the laptop leaves the desktop as it was.

```sh
coffer config list feature.
coffer config set feature.vault_sync on
coffer config set feature.memory off
coffer config unset feature.memory        # back to the channel default
```

The same switch is `PUT /api/v1/daemon/features/{key}`. Settings in the web UI lists no features: at 1.0 every experimental feature graduates and its switch is deleted.

`config list feature.` shows each feature's state and what decided it:

```text
Key                  Value                      Default   Type
feature.vault_sync   on (set on this machine)   channel   on|off
feature.knowledge    off (channel default)      channel   on|off
feature.memory       off (channel default)      channel   on|off
```

The sidebar entry of a feature you switch on appears in an open web UI without a reload.

The `feature.*` keys go through the running daemon, because only it can make a switch take effect immediately. Add `--json` to `config list` for scripts.

## How a feature's state is decided

For each feature, the first of these that has an answer wins:

1. **A pin** in the `COFFER_FEATURES` environment variable of the daemon process.
2. **This machine's setting**, written by the switch above.
3. **The channel default**: off on `stable`, on on `dev`.

### Pin a feature with `COFFER_FEATURES`

`COFFER_FEATURES` fixes features for the lifetime of one daemon, which is useful for tests and scripted setups:

```sh
COFFER_FEATURES=vault_sync=on,memory=off coffer daemon restart
```

Entries are comma-separated `key=value` pairs; `on`, `true` and `1` switch a feature on, `off`, `false` and `0` switch it off. An unknown key or a malformed entry is logged as a warning and ignored.

A pinned feature cannot be switched: a write answers `409 FEATURE_PINNED`. The variable must be in the environment of the process that starts the daemon. The daemon is started by whichever surface needs it first (a CLI command, an agent's MCP shim, the desktop app, the login service), so a variable exported in one shell does not reach a daemon started from elsewhere.

## What "off" means

Switching a feature off closes it everywhere on this machine:

- **REST:** its routes answer `404` with the code `FEATURE_DISABLED` and the feature's key. Resources of a kind the feature owns (`knowledge` collections, `memory` partitions) are also hidden from the generic `/api/v1/resources` routes.
- **CLI:** its commands print one line and exit 1:
  ```text
  vault_sync is switched off on this machine — run: coffer config set feature.vault_sync on
  ```
- **MCP:** its tools leave the tool list, and a call to one answers as an unknown tool. The handshake instructions and the `coffer-guide` skill stop mentioning them.
- **Web UI:** its sidebar entry disappears, and its pages show a notice ("Knowledge is switched off") naming the command that switches it back on.
- **Background passes:** its passes skip their rounds.

Some features also withdraw what they placed in front of agents:

- Switching `memory` off removes the memory delivery hook from every agent it was installed in; switching it on installs it into every agent connected to Coffer.
- Switching `knowledge` off rewrites `coffer-guide` without the knowledge catalogue, and a channel `/kb` replies that knowledge is switched off instead of saving; `/kb` also leaves the channel's help and command menus.
- Switching `vault_sync` off stops every sync attention mark in the web UI and the desktop app and removes the tray's Sync item. While it is off, the knowledge curation pass treats the vault as a single-machine one.

::: tip Nothing is deleted
Switching a feature off never deletes, moves or rewrites what it holds: collections and their files, memory partitions, a configured sync remote, history. Switch it back on and it resumes from exactly that state. Database migrations run whatever the switches say, so switching a feature on never needs a schema change.
:::

## How it works

Coffer keeps every capability on one line of development and gates the unfinished ones instead of maintaining a separate release branch. The trade-offs are recorded in [Experimental Features Instead of a Release Branch](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/experimental-features-instead-of-a-release-branch.md). A feature leaves the registry once it is ready, and its gates are removed.

## Related

- [Running the daemon](/guides/daemon)
- [Vault sync](/guides/vault-sync) · [Knowledge](/guides/knowledge) · [Memory](/guides/memory)
- [Configuration reference](/reference/configuration)
- [Error codes](/reference/error-codes)
- Spec: [experimental-features](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/experimental-features/spec.md)
