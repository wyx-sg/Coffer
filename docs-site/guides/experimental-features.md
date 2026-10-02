---
title: Experimental features
description: The four capabilities that ship switched off — Knowledge, Memory, Sync and Model providers — how to switch each one on per machine from Settings, the CLI or COFFER_FEATURES, and what a switched-off feature looks like.
---

# Experimental features

Coffer ships one build with every capability in it. A few capabilities are not proven yet, so they start **switched off** and you decide, machine by machine, which ones to try. This page explains the four experimental features and what you see while one is off.

A stable release and a build from source behave the same way here: every experimental feature is off until you switch it on.

## The four features

| Key | Name | What it covers |
| --- | --- | --- |
| `knowledge` | Knowledge | The Knowledge page and its files, the `coffer__write` tool, and the knowledge sections of the `coffer-guide` skill. |
| `memory` | Memory | The Memory page, the memory delivery hook in your agents, and memory in channel turns. |
| `sync` | Sync | Vault sync to your own git remote. |
| `models` | Model providers | Model providers, the local model proxy and Usage, and the projection of connections into your agents' own config files. |

Everything else is always on: the app shell, Overview, Agents, the MCP gateway and custom tools, Skills, Secrets, Activity, Settings, Conversations and Channels. The agent list and its model catalogue, Coffer's own model settings, the vault and an agent's own transcripts and memory files are not gated either.

### How the features relate

No feature needs another. When one is off, the others keep working:

| When this is off | What happens |
| --- | --- |
| `knowledge` | The Knowledge page and its API are gone, `coffer__write` is hidden, the `coffer-guide` skill has no knowledge catalogue, curation skips, and a channel's `/kb` answers that Knowledge is switched off. Memory is unaffected. |
| `memory` | The Memory page and its API are gone, the handshake does not name the memory root, the memory hook is taken out of your agents (and put back when you switch it on), distil and aggregate skip, and channel turns carry no memory. Knowledge is unaffected. |
| `sync` | The vault is single-machine for curation. |
| `models` | The local proxy and Usage are gone, and Coffer's keys are taken out of your agents' own configs, so agents use their own login. Knowledge and memory keep working on the model connection already chosen for Coffer's engine. |

## Switch a feature on or off

Every feature is off by default. You switch it on for this machine in either of two places:

- **Settings → Features** lists the four features, each with an **Experimental** mark, a one-line description and an on/off switch. The tab is in every build. If the feature is pinned (below), the switch is disabled and says so.
- **`coffer config`** has a `feature.<key>` key for each feature:

```sh
coffer config list feature.            # every feature, its state, and what decided it
coffer config set feature.models on
coffer config set feature.models off
coffer config unset feature.models     # back to off
```

```text
feature.knowledge = off (default)
feature.memory = on (setting)
feature.sync = off (pin)
feature.models = off (default)
```

A switch takes effect at once, with no restart, and is kept in `~/.coffer/daemon-config.json` on this machine only. It never syncs, so switching a feature on in your laptop leaves your desktop as it was. The same switch is `PUT /api/v1/daemon/features/{key}`, and `DELETE` on that path returns it to off.

Settings that name a feature Coffer does not know are ignored, and a request for an unknown key is refused with `FEATURE_UNKNOWN`.

## How a feature's state is decided

For each feature, the first of these that has an answer wins:

1. **A pin** in the `COFFER_FEATURES` environment variable of the daemon process.
2. **This machine's setting**, written by the switch above.
3. **The default**, which is off for every feature.

The listing shows which one decided each feature: `pin`, `setting` or `default`.

### Pin a feature with `COFFER_FEATURES`

`COFFER_FEATURES` fixes features for the lifetime of one daemon, which is useful for tests and scripted setups:

```sh
COFFER_FEATURES=knowledge=on,models=off coffer daemon restart
```

Entries are comma-separated `key=value` pairs; `on`, `true` and `1` switch a feature on, `off`, `false` and `0` switch it off. An unknown key or a malformed entry is logged as a warning and ignored.

A pinned feature cannot be switched: a write answers `409 FEATURE_PINNED`. The variable must be in the environment of the process that starts the daemon. The daemon is started by whichever surface needs it first (a CLI command, an agent's MCP shim, the desktop app, the login service), so a variable exported in one shell does not reach a daemon started from elsewhere.

## What "off" looks like

A switched-off feature looks absent. Nothing in the web UI mentions it:

- **Web UI:** its sidebar entries are gone (and a group left with no entries disappears), it is not in the command palette, its tiles and first-run cards are not on Overview, and no other page shows a section for it. A link straight to one of its pages shows the standard not-found page. There is no notice and no **Switch on** button outside Settings → Features.
- **REST:** its routes answer `404` with the code `FEATURE_DISABLED` and the feature's key. Resources of a kind the feature owns are also hidden from the generic `/api/v1/resources` routes.
- **CLI:** its commands print one line naming `coffer config set feature.<key> on` and exit 1.
- **MCP:** a built-in tool that belongs to the feature leaves the tool list, and a call to one answers as an unknown tool.
- **Background passes:** its passes skip their rounds.

While a feature is on, its sidebar entries carry an **Experimental** label, so nobody takes it for a finished part of the product.

::: tip Nothing is deleted
Switching a feature off never deletes, moves or rewrites what it holds. Switch it back on and it resumes from exactly that state. Database migrations run whatever the switches say, so switching a feature on never needs a schema change.
:::

## How it works

Keeping unfinished work behind a registry entry, rather than on a separate release branch, is recorded in [Experimental Features Instead of a Release Branch](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/experimental-features-instead-of-a-release-branch.md). The architecture is in [Distribution and releases](/architecture/distribution#experimental-features).

## Related

- [Running the daemon](/guides/daemon)
- [Configuration reference](/reference/configuration)
- [Error codes](/reference/error-codes)
- Spec: [experimental-features](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/experimental-features/spec.md)
