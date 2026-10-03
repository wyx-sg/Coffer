---
title: coffer sync
description: "Keep this vault in step with a git remote you own"
pageClass: cli-ref
---

# coffer sync

Keep this vault in step with a git remote you own

```sh
coffer sync [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer sync --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`sync now`](#sync-now) | Run one round with the remote, right now. |
| [`sync status`](#sync-status) | The remote, the last round, and anything waiting for you. |
| [`sync push-anyway`](#sync-push-anyway) | Push what the last round refused as a plaintext secret, once you checked it is not one. |
| [`sync history`](#sync-history) | Every round this machine has run, newest first, one line each. |
| [`sync rollback`](#sync-rollback) | Put back what one round changed, from its snapshot. |
| [`sync join`](#sync-join) | Join the configured remote. |
| [`sync conflicts`](#sync-conflicts) | The files the stopped round waits on (or the held deletions). |
| [`sync resolve`](#sync-resolve) | Answer one conflicting file. |
| [`sync edit`](#sync-edit) | Print the path of a marked-up copy of the file to hand-merge; then 'coffer sync resolve PATH --edited'. |
| [`sync continue`](#sync-continue) | Continue the stopped round once every file has an answer. |
| [`sync hold`](#sync-hold) | Show a held round, or answer it: --confirm deletes the files, --restore keeps them. |
| [`sync choose`](#sync-choose) | Settle a file a join found different on both sides. |
| [`sync remote`](#sync-remote) | The one git remote this vault syncs with |
| [`sync remote set`](#sync-remote-set) | Configure the remote ('coffer sync remote check' looks at it first). |
| [`sync remote clear`](#sync-remote-clear) | Stop syncing: forget the remote. |
| [`sync remote pause`](#sync-remote-pause) | Pause sync. |
| [`sync remote resume`](#sync-remote-resume) | Resume a paused remote where the vault left off. |
| [`sync remote check`](#sync-remote-check) | Look at a remote without keeping it: empty, a Coffer vault (and its layout), another repository, unreachable, or refusing the token. |
| [`sync machine`](#sync-machine) | The machines sharing this vault |
| [`sync machine list`](#sync-machine-list) | Every machine sharing this vault. |
| [`sync machine rename`](#sync-machine-rename) | Rename this machine. |
| [`sync machine rm`](#sync-machine-rm) | Retire another machine: its descriptor goes, in a commit of yours that the next round pushes. |
| [`sync key`](#sync-key) | Install a master key brought from another machine, or compare fingerprints. |
| [`sync key import`](#sync-key-import) | Install a master key brought from another machine. |
| [`sync key fingerprint`](#sync-key-fingerprint) | This machine's key fingerprint, to compare with another machine's. |

## sync now

Run one round with the remote, right now.

<p class="cli-label">Synopsis</p>

```sh
coffer sync now [OPTIONS]
```

## sync status

The remote, the last round, and anything waiting for you.

Exits 1 while a round waits for a person — stopped on conflicts, held, unable to reach or sign in to the remote, or paused because the vault is inside a synchronised folder — so a prompt or a monitor notices without reading the text. A paused remote exits 0.

<p class="cli-label">Synopsis</p>

```sh
coffer sync status [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |
| `--prompt` <span class="cli-chip">option</span> | flag |  | Print the prompt that hands the current problem (a refused push or sign-in, an unreachable remote, git missing, a plaintext secret in what a push would publish) to your agent |

## sync push-anyway

Push what the last round refused as a plaintext secret, once you checked it is not one.

Allows exactly the file versions that round found (a file changed since is read again), records it in the audit log, and runs a round.

<p class="cli-label">Synopsis</p>

```sh
coffer sync push-anyway [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--yes, -y` <span class="cli-chip">option</span> | flag |  | Do not ask before pushing |

## sync history

Every round this machine has run, newest first, one line each.

<p class="cli-label">Synopsis</p>

```sh
coffer sync history [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--limit` <span class="cli-chip">option</span> | integer | `20` | How many rounds to show, newest first |

## sync rollback

Put back what one round changed, from its snapshot.

The plan is printed first. Rolling back is a new commit on this machine, which the next round pushes; files edited since the round are kept.

<p class="cli-label">Synopsis</p>

```sh
coffer sync rollback [OPTIONS] RUN_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `RUN_ID` <span class="cli-chip">argument</span> | integer | required | The round to roll back (see coffer sync history) |
| `--yes, -y` <span class="cli-chip">option</span> | flag |  | Do not ask before rolling back |

## sync join

Join the configured remote. What joining would do is printed first; joining never deletes a file on either side, except that this vault replaces a remote at an older layout (the old history stays in git).

<p class="cli-label">Synopsis</p>

```sh
coffer sync join [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--yes, -y` <span class="cli-chip">option</span> | flag |  | Do not ask before joining |

## sync conflicts

The files the stopped round waits on (or the held deletions).

<p class="cli-label">Synopsis</p>

```sh
coffer sync conflicts [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--prompt` <span class="cli-chip">option</span> | flag |  | Print the prompt that hands merging the conflicting files to your agent |

## sync resolve

Answer one conflicting file. Nothing is written until 'continue'.

<p class="cli-label">Synopsis</p>

```sh
coffer sync resolve [OPTIONS] PATH
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">argument</span> | text | required | Vault-relative path of a conflicting file |
| `--mine` <span class="cli-chip">option</span> | flag |  | Keep this machine's version |
| `--theirs` <span class="cli-chip">option</span> | flag |  | Take the other machine's version |
| `--edited` <span class="cli-chip">option</span> | flag |  | Take the merged copy 'coffer sync edit' opened, or an agent's merge of it |

## sync edit

Print the path of a marked-up copy of the file to hand-merge; then 'coffer sync resolve PATH --edited'. The vault's file is untouched. With --discard, the copy (and an agent's merge in it) is thrown away and the file waits for a choice again.

<p class="cli-label">Synopsis</p>

```sh
coffer sync edit [OPTIONS] PATH
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">argument</span> | text | required | Vault-relative path of a conflicting file |
| `--join` <span class="cli-chip">option</span> | flag |  | The file is one a join found different (then 'choose --edited') |
| `--discard` <span class="cli-chip">option</span> | flag |  | Forget the marked-up copy and any agent's merge: back to two choices |

## sync continue

Continue the stopped round once every file has an answer.

<p class="cli-label">Synopsis</p>

```sh
coffer sync continue [OPTIONS]
```

## sync hold

Show a held round, or answer it: --confirm deletes the files, --restore keeps them. Either continues the round.

<p class="cli-label">Synopsis</p>

```sh
coffer sync hold [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--confirm` <span class="cli-chip">option</span> | flag |  | Delete the held files |
| `--restore` <span class="cli-chip">option</span> | flag |  | Keep the held files |

## sync choose

Settle a file a join found different on both sides.

<p class="cli-label">Synopsis</p>

```sh
coffer sync choose [OPTIONS] [PATH]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">argument</span> | text |  | A file that differs (omit to list them) |
| `--mine` <span class="cli-chip">option</span> | flag |  | Keep this machine's version |
| `--theirs` <span class="cli-chip">option</span> | flag |  | Take the remote's version |
| `--edited` <span class="cli-chip">option</span> | flag |  | Take the merged copy 'coffer sync edit' opened |

## sync remote

The one git remote this vault syncs with

<p class="cli-label">Synopsis</p>

```sh
coffer sync remote [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `set`, `clear`, `pause`, `resume`, `check`.

## sync remote set

Configure the remote ('coffer sync remote check' looks at it first).

On a configured remote an option not given keeps its stored value, and a paused remote stays paused (`coffer sync remote resume` resumes it). A remote set for the first time takes the defaults and starts enabled.

<p class="cli-label">Synopsis</p>

```sh
coffer sync remote set [OPTIONS] URL
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `URL` <span class="cli-chip">argument</span> | text | required | Git remote URL you own (https, ssh, or file://) |
| `--branch` <span class="cli-chip">option</span> | text |  | Default main |
| `--interval` <span class="cli-chip">option</span> | integer |  | Seconds between automatic rounds (default 3600) |
| `--with-secret / --without-secret` <span class="cli-chip">option</span> | boolean |  | Carry the encrypted secrets (ciphertext, never the master key); default off |
| `--secret-ref` <span class="cli-chip">option</span> | text |  | Name of the push token in the secret store ('' removes it) |
| `--username` <span class="cli-chip">option</span> | text |  | User name an HTTPS token is sent with, for a host that does not imply it (default coffer; GitLab: oauth2 or your user name; Bitbucket and Azure DevOps need a real one) |
| `--wait` <span class="cli-chip">option</span> | flag |  | Wait for approval in the Coffer app instead of exiting |

## sync remote clear

Stop syncing: forget the remote. The vault is left exactly as it is.

<p class="cli-label">Synopsis</p>

```sh
coffer sync remote clear [OPTIONS]
```

## sync remote pause

Pause sync. The remote, its settings and the history are all kept.

<p class="cli-label">Synopsis</p>

```sh
coffer sync remote pause [OPTIONS]
```

## sync remote resume

Resume a paused remote where the vault left off.

<p class="cli-label">Synopsis</p>

```sh
coffer sync remote resume [OPTIONS]
```

## sync remote check

Look at a remote without keeping it: empty, a Coffer vault (and its layout), another repository, unreachable, or refusing the token.

<p class="cli-label">Synopsis</p>

```sh
coffer sync remote check [OPTIONS] [URL]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `URL` <span class="cli-chip">argument</span> | text |  | A remote to look at (default: the stored one) |
| `--branch` <span class="cli-chip">option</span> | text |  | Default main |
| `--secret-ref` <span class="cli-chip">option</span> | text |  | Push token to use |
| `--username` <span class="cli-chip">option</span> | text |  | User name the token is sent with (default: the stored one, else coffer; GitLab: oauth2 or your user name) |

## sync machine

The machines sharing this vault

<p class="cli-label">Synopsis</p>

```sh
coffer sync machine [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `list`, `rename`, `rm`.

## sync machine list

Every machine sharing this vault.

<p class="cli-label">Synopsis</p>

```sh
coffer sync machine list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## sync machine rename

Rename this machine. Free: nothing keys on the label; the next round carries the new one.

<p class="cli-label">Synopsis</p>

```sh
coffer sync machine rename [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required |  |

## sync machine rm

Retire another machine: its descriptor goes, in a commit of yours that the next round pushes. A machine that syncs again comes back.

<p class="cli-label">Synopsis</p>

```sh
coffer sync machine rm [OPTIONS] MACHINE_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `MACHINE_ID` <span class="cli-chip">argument</span> | text | required |  |

## sync key

Install a master key brought from another machine, or compare fingerprints. Exporting a key backup is done in the Coffer desktop app.

<p class="cli-label">Synopsis</p>

```sh
coffer sync key [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `import`, `fingerprint`.

## sync key import

Install a master key brought from another machine.

A ``.cfk`` backup asks for the passphrase it was exported with, without echoing it.

<p class="cli-label">Synopsis</p>

```sh
coffer sync key import [OPTIONS] PATH
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">argument</span> | text | required | The key backup (coffer-master-key.cfk) exported from another machine, or a bare key |

## sync key fingerprint

This machine's key fingerprint, to compare with another machine's.

<p class="cli-label">Synopsis</p>

```sh
coffer sync key fingerprint [OPTIONS]
```
