---
title: Experimental features
description: How Coffer ships a capability that is not ready yet — the registry, the release channel that sets its default, and switching it per machine from Settings, the CLI or COFFER_FEATURES. No feature is experimental right now.
---

# Experimental features

Coffer keeps every capability on one line of development. When a new capability is not ready for everyone yet, it still ships in every build, but as an **experimental feature**: off by default in a release build, on by default in a build from source, and switchable on each machine. This page explains how that works, so you know what to expect when a feature is experimental.

::: info No feature is experimental right now
The registry is empty. Sync, Knowledge and Memory were experimental before 1.0 and graduated at 1.0: they are always on, in every build, and have no switch. **Settings → General** shows no experimental-features section, no sidebar entry carries an **Experimental** label, and `coffer config list feature.` lists nothing.
:::

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
version: 1.0.0
channel: stable
port:    8000
pid:     41822
```

The channel only sets the default of experimental features. With the registry empty, both channels behave the same.

## Switch a feature on or off

While a feature is registered, it shows up in three places:

- **Settings → General** gets an experimental-features section with one switch per feature.
- **The sidebar** labels the feature's entry **Experimental**, so nobody takes it for a finished part of the product.
- **`coffer config`** gets a `feature.<key>` key:

```sh
coffer config list feature.            # every feature, its state, and what decided it
coffer config set feature.<key> on
coffer config set feature.<key> off
coffer config unset feature.<key>      # back to the channel default
```

A switch takes effect at once, with no restart, and is kept in `~/.coffer/daemon-config.json` on this machine only. It is never synced, so switching a feature on the laptop leaves the desktop as it was. The same switch is `PUT /api/v1/daemon/features/{key}`, and `DELETE` on that path goes back to the channel default. The `feature.*` keys go through the running daemon, because only it can make a switch take effect immediately.

A key the registry does not declare is refused: the REST route answers `FEATURE_UNKNOWN`, and `coffer config set feature.<key>` reports an unknown setting. That is what `coffer config set feature.knowledge off` answers now that Knowledge has graduated.

## How a feature's state is decided

For each feature, the first of these that has an answer wins:

1. **A pin** in the `COFFER_FEATURES` environment variable of the daemon process.
2. **This machine's setting**, written by the switch above.
3. **The channel default**: off on `stable`, on on `dev`.

### Pin a feature with `COFFER_FEATURES`

`COFFER_FEATURES` fixes features for the lifetime of one daemon, which is useful for tests and scripted setups:

```sh
COFFER_FEATURES=<key>=on,<other-key>=off coffer daemon restart
```

Entries are comma-separated `key=value` pairs; `on`, `true` and `1` switch a feature on, `off`, `false` and `0` switch it off. An unknown key or a malformed entry is logged as a warning and ignored, so an old pin that names a graduated feature is harmless.

A pinned feature cannot be switched: a write answers `409 FEATURE_PINNED`. The variable must be in the environment of the process that starts the daemon. The daemon is started by whichever surface needs it first (a CLI command, an agent's MCP shim, the desktop app, the login service), so a variable exported in one shell does not reach a daemon started from elsewhere.

## What "off" means

Switching a feature off closes it everywhere on this machine:

- **REST:** its routes answer `404` with the code `FEATURE_DISABLED` and the feature's key. Resources of a kind the feature owns are also hidden from the generic `/api/v1/resources` routes.
- **CLI:** its commands print one line naming `coffer config set feature.<key> on` and exit 1.
- **MCP:** a built-in tool that belongs to the feature leaves the tool list, and a call to one answers as an unknown tool.
- **Web UI:** its sidebar entry disappears, and its pages show a notice naming the command that switches it back on.
- **Background passes:** its passes skip their rounds.

A feature that placed something in front of agents, such as a hook in an agent's config, withdraws it when switched off and puts it back when switched on.

::: tip Nothing is deleted
Switching a feature off never deletes, moves or rewrites what it holds. Switch it back on and it resumes from exactly that state. Database migrations run whatever the switches say, so switching a feature on never needs a schema change.
:::

## How a feature joins and leaves

A feature **joins** by adding one entry to the registry, [`backend/coffer/domain/features.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/domain/features.py). The entry names the feature's key, the REST route prefixes it owns and the resource kinds it owns. Every surface reads that one list: routes under its prefixes and resources of its kinds are gated, a built-in MCP tool that names the feature leaves the tool list while it is off, a sidebar entry that names it gets the Experimental label and hides while it is off, and its background passes check it each round. The Settings section and `coffer config list feature.` pick it up with no further work.

A feature **leaves** by graduating once it is ready. Its registry entry is deleted, every gate that names it is deleted, and a migration strips its stored setting from `daemon-config.json`. From then on it is simply part of Coffer, and its old key is unknown. Sync, Knowledge and Memory left this way at 1.0.

## How it works

Keeping unfinished work behind a registry entry, rather than on a separate release branch, is recorded in [Experimental Features Instead of a Release Branch](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/experimental-features-instead-of-a-release-branch.md). The architecture is in [Distribution and releases](/architecture/distribution#experimental-features).

## Related

- [Running the daemon](/guides/daemon)
- [Configuration reference](/reference/configuration)
- [Error codes](/reference/error-codes)
- Spec: [experimental-features](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/experimental-features/spec.md)
