---
title: coffer sync
description: "Vault sync: remote, rounds, machines, conflicts."
pageClass: cli-ref
---

# coffer sync

Vault sync: remote, rounds, machines, conflicts.

```sh
coffer sync [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer sync --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`sync status`](#sync-status) | The remote, the last and next round, what waits, and what needs you. |
| [`sync run`](#sync-run) | Run one round now and print how it ended (waits for it). |
| [`sync continue`](#sync-continue) | Continue a round that stopped for you. |
| [`sync runs`](#sync-runs) | Every round this machine ran, newest first. |
| [`sync run-diff`](#sync-run-diff) | What a round changed in one file. |
| [`sync rollback-plan`](#sync-rollback-plan) | What rolling a round back would change. |
| [`sync rollback`](#sync-rollback) | Roll a round back. |
| [`sync join-preview`](#sync-join-preview) | What joining the remote's vault would change here. |
| [`sync join`](#sync-join) | Join the remote's vault. |
| [`sync join-choices`](#sync-join-choices) | Files where this machine and the remote differ on joining. |
| [`sync join-choose`](#sync-join-choose) | Choose a side per file. |
| [`sync join-discard`](#sync-join-discard) | Body: path. |
| [`sync join-handoff`](#sync-join-handoff) | The prompt that hands the choices to an agent. |
| [`sync stop`](#sync-stop) | Why the round stopped and what it asks. |
| [`sync file-versions`](#sync-file-versions) | Both versions of a file. |
| [`sync file-answer`](#sync-file-answer) | Answer for one file. |
| [`sync file-discard`](#sync-file-discard) | Body: path. |
| [`sync stop-handoff`](#sync-stop-handoff) | The prompt that hands resolving to an agent. |
| [`sync hold-diff`](#sync-hold-diff) | A change held for confirmation, one file. |
| [`sync hold-confirm`](#sync-hold-confirm) | Apply the held changes. |
| [`sync hold-restore`](#sync-hold-restore) | Put back what the held round would delete. |
| [`sync pending-diff`](#sync-pending-diff) | A local change waiting to be pushed, one file. |
| [`sync plaintext-context`](#sync-plaintext-context) | The lines around a plaintext secret. |
| [`sync push-anyway`](#sync-push-anyway) | Push although a file holds plaintext. |
| [`sync machines`](#sync-machines) | Every machine in the vault. |
| [`sync vault-move`](#sync-vault-move) | Move the vault's files out of a synchronised folder. |
| [`sync wait`](#sync-wait) | Wait for the round now running to end and print the status (exit 13 on timeout). |
| [`sync remote`](#sync-remote) | The git remote the vault syncs with. |
| [`sync remote set`](#sync-remote-set) | Set the remote. |
| [`sync remote check`](#sync-remote-check) | Check a remote before saving it. |
| [`sync remote delete`](#sync-remote-delete) | Forget the remote (the local vault stays). |
| [`sync remote restore`](#sync-remote-restore) | Rebuild the remote from this machine's vault. |
| [`sync machine`](#sync-machine) | One machine of the vault: rename, retire, restore. |
| [`sync machine rename`](#sync-machine-rename) | Rename this machine. |
| [`sync machine retire`](#sync-machine-retire) | Retire a machine. |
| [`sync machine restore`](#sync-machine-restore) | Bring a retired machine back. |

## sync status

The remote, the last and next round, what waits, and what needs you.

<p class="cli-label">Synopsis</p>

```sh
coffer sync status [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync run

Run one round now and print how it ended (waits for it).

<p class="cli-label">Synopsis</p>

```sh
coffer sync run [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync continue

Continue a round that stopped for you.

<p class="cli-label">Synopsis</p>

```sh
coffer sync continue [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync runs

Every round this machine ran, newest first.

<p class="cli-label">Synopsis</p>

```sh
coffer sync runs [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--limit` <span class="cli-chip">option</span> | integer |  |  |
| `--cursor` <span class="cli-chip">option</span> | text |  |  |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync run-diff

What a round changed in one file.

<p class="cli-label">Synopsis</p>

```sh
coffer sync run-diff [OPTIONS] RUN_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `RUN_ID` <span class="cli-chip">argument</span> | text | required | run id |
| `--path` <span class="cli-chip">option</span> | text |  | A path under the vault |
| `--side` <span class="cli-chip">option</span> | text |  |  |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync rollback-plan

What rolling a round back would change.

<p class="cli-label">Synopsis</p>

```sh
coffer sync rollback-plan [OPTIONS] RUN_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `RUN_ID` <span class="cli-chip">argument</span> | text | required | run id |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync rollback

Roll a round back.

<p class="cli-label">Synopsis</p>

```sh
coffer sync rollback [OPTIONS] RUN_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `RUN_ID` <span class="cli-chip">argument</span> | text | required | run id |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync join-preview

What joining the remote's vault would change here.

<p class="cli-label">Synopsis</p>

```sh
coffer sync join-preview [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync join

Join the remote's vault.

<p class="cli-label">Synopsis</p>

```sh
coffer sync join [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync join-choices

Files where this machine and the remote differ on joining.

<p class="cli-label">Synopsis</p>

```sh
coffer sync join-choices [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync join-choose

Choose a side per file. Body: choices.

<p class="cli-label">Synopsis</p>

```sh
coffer sync join-choose [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync join-discard

Body: path.

<p class="cli-label">Synopsis</p>

```sh
coffer sync join-discard [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync join-handoff

The prompt that hands the choices to an agent. Body: paths, agent.

<p class="cli-label">Synopsis</p>

```sh
coffer sync join-handoff [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync stop

Why the round stopped and what it asks.

<p class="cli-label">Synopsis</p>

```sh
coffer sync stop [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync file-versions

Both versions of a file.

<p class="cli-label">Synopsis</p>

```sh
coffer sync file-versions [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--path` <span class="cli-chip">option</span> | text |  | A path under the vault |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync file-answer

Answer for one file. Body: path, answer (mine | theirs | edited); edited keeps the copy you resolved in your editor.

<p class="cli-label">Synopsis</p>

```sh
coffer sync file-answer [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync file-discard

Body: path.

<p class="cli-label">Synopsis</p>

```sh
coffer sync file-discard [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync stop-handoff

The prompt that hands resolving to an agent. Body: paths, agent.

<p class="cli-label">Synopsis</p>

```sh
coffer sync stop-handoff [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync hold-diff

A change held for confirmation, one file.

<p class="cli-label">Synopsis</p>

```sh
coffer sync hold-diff [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--path` <span class="cli-chip">option</span> | text |  | A path under the vault |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync hold-confirm

Apply the held changes.

<p class="cli-label">Synopsis</p>

```sh
coffer sync hold-confirm [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync hold-restore

Put back what the held round would delete.

<p class="cli-label">Synopsis</p>

```sh
coffer sync hold-restore [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync pending-diff

A local change waiting to be pushed, one file.

<p class="cli-label">Synopsis</p>

```sh
coffer sync pending-diff [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--path` <span class="cli-chip">option</span> | text |  | A path under the vault |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync plaintext-context

The lines around a plaintext secret.

<p class="cli-label">Synopsis</p>

```sh
coffer sync plaintext-context [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--path` <span class="cli-chip">option</span> | text |  | A path under the vault |
| `--line` <span class="cli-chip">option</span> | integer |  |  |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync push-anyway

Push although a file holds plaintext.

<p class="cli-label">Synopsis</p>

```sh
coffer sync push-anyway [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync machines

Every machine in the vault.

<p class="cli-label">Synopsis</p>

```sh
coffer sync machines [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync vault-move

Move the vault's files out of a synchronised folder. Body: to.

<p class="cli-label">Synopsis</p>

```sh
coffer sync vault-move [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync wait

Wait for the round now running to end and print the status (exit 13 on timeout).

<p class="cli-label">Synopsis</p>

```sh
coffer sync wait [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--timeout` <span class="cli-chip">option</span> | float | `600.0` | Seconds to wait |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync remote

The git remote the vault syncs with.

<p class="cli-label">Synopsis</p>

```sh
coffer sync remote [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `set`, `check`, `delete`, `restore`.

## sync remote set

Set the remote. Body: url, branch, secret_ref, include_secret, enabled, interval_seconds.

<p class="cli-label">Synopsis</p>

```sh
coffer sync remote set [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync remote check

Check a remote before saving it. Body: url, branch, secret_ref.

<p class="cli-label">Synopsis</p>

```sh
coffer sync remote check [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync remote delete

Forget the remote (the local vault stays).

<p class="cli-label">Synopsis</p>

```sh
coffer sync remote delete [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync remote restore

Rebuild the remote from this machine's vault.

<p class="cli-label">Synopsis</p>

```sh
coffer sync remote restore [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync machine

One machine of the vault: rename, retire, restore.

<p class="cli-label">Synopsis</p>

```sh
coffer sync machine [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `rename`, `retire`, `restore`.

## sync machine rename

Rename this machine. Body: name.

<p class="cli-label">Synopsis</p>

```sh
coffer sync machine rename [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync machine retire

Retire a machine.

<p class="cli-label">Synopsis</p>

```sh
coffer sync machine retire [OPTIONS] MACHINE_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `MACHINE_ID` <span class="cli-chip">argument</span> | text | required | machine id |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## sync machine restore

Bring a retired machine back.

<p class="cli-label">Synopsis</p>

```sh
coffer sync machine restore [OPTIONS] MACHINE_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `MACHINE_ID` <span class="cli-chip">argument</span> | text | required | machine id |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
